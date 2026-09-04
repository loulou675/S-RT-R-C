#!/usr/bin/env python3
"""Add balanced Organic crops and food-part boxes from Open Images V7.

The source annotations use normalized bounding boxes. Each selected source
image stays in one deterministic split so crops and detector images cannot leak
between train, validation and test.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "training" / "classifier_dataset"
RAW_DATASET = ROOT / "training" / "dataset"
COMPONENTS = ROOT / "training" / "component_dataset"
MANIFEST = ROOT / "training" / "source_manifests" / "openimages-organic-sources.jsonl"
CACHE = Path("/tmp/sort-rac-openimages")
CLASSES_URL = "https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions-boxable.csv"
BOXES_URL = "https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv"
IMAGE_URL = "https://open-images-dataset.s3.amazonaws.com/validation/{image_id}.jpg"
USER_AGENT = "sort-rac-organic-training/1.0"

TARGET_GROUPS = {
    "food_waste": {
        "Food",
        "Fast food",
        "Pizza",
        "Bread",
        "Salad",
        "Sandwich",
        "Submarine sandwich",
        "Hot dog",
        "Pancake",
        "Cake",
        "Egg",
        "Seafood",
    },
    "fruit_peel": {"Fruit", "Apple", "Banana", "Orange (fruit)", "Pineapple", "Grapefruit"},
    "vegetable_scraps": {"Vegetable", "Tomato", "Potato", "Cabbage", "Carrot", "Broccoli"},
}
GENERAL_LABELS = {"Food", "Fruit", "Vegetable"}
SPLIT_QUOTAS = {"train": 150, "val": 20, "test": 20}


def download_metadata(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 1000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120, stream=True) as response:
        response.raise_for_status()
        with path.open("wb") as target:
            for chunk in response.iter_content(1024 * 1024):
                target.write(chunk)


def stable_split(image_id: str) -> str:
    bucket = int(hashlib.sha256(f"organic:{image_id}".encode()).hexdigest()[:8], 16) % 100
    if bucket < 79:
        return "train"
    if bucket < 90:
        return "val"
    return "test"


def annotation_area(row: dict[str, str]) -> float:
    return max(0.0, float(row["XMax"]) - float(row["XMin"])) * max(
        0.0, float(row["YMax"]) - float(row["YMin"])
    )


def usable(row: dict[str, str]) -> bool:
    return (
        row.get("IsDepiction") != "1"
        and row.get("IsInside") != "1"
        and row.get("IsGroupOf") != "1"
        and annotation_area(row) >= 0.012
    )


def iou(left: dict[str, str], right: dict[str, str]) -> float:
    x1 = max(float(left["XMin"]), float(right["XMin"]))
    y1 = max(float(left["YMin"]), float(right["YMin"]))
    x2 = min(float(left["XMax"]), float(right["XMax"]))
    y2 = min(float(left["YMax"]), float(right["YMax"]))
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = annotation_area(left) + annotation_area(right) - intersection
    return intersection / union if union else 0.0


def merge_overlapping(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    kept: list[dict[str, str]] = []
    for row in sorted(rows, key=annotation_area, reverse=True):
        if any(iou(row, existing) >= 0.65 for existing in kept):
            continue
        kept.append(row)
    return kept


def download_image(image_id: str) -> tuple[Image.Image, str] | None:
    url = IMAGE_URL.format(image_id=image_id)
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(10, 45))
        response.raise_for_status()
        image = ImageOps.exif_transpose(Image.open(BytesIO(response.content))).convert("RGB")
        if min(image.size) < 160:
            return None
        return image, url
    except (requests.RequestException, UnidentifiedImageError, OSError):
        return None


def crop_box(image: Image.Image, row: dict[str, str], padding: float = 0.16) -> Image.Image | None:
    x1 = float(row["XMin"]) * image.width
    x2 = float(row["XMax"]) * image.width
    y1 = float(row["YMin"]) * image.height
    y2 = float(row["YMax"]) * image.height
    width, height = x2 - x1, y2 - y1
    pad = max(width, height) * padding
    box = (
        max(0, int(x1 - pad)),
        max(0, int(y1 - pad)),
        min(image.width, int(x2 + pad)),
        min(image.height, int(y2 + pad)),
    )
    crop = image.crop(box)
    return crop if min(crop.size) >= 96 else None


def select_records(rows_by_image: dict[str, list[dict[str, str]]]) -> dict[str, dict]:
    selected: dict[str, dict] = {}
    counts = {group: {split: 0 for split in SPLIT_QUOTAS} for group in TARGET_GROUPS}
    candidates: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)

    for image_id, rows in rows_by_image.items():
        by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            by_group[row["target_group"]].append(row)
        for group, group_rows in by_group.items():
            # Prefer a specific food label over a broad parent box.
            best = max(group_rows, key=lambda row: (row["display_name"] not in GENERAL_LABELS, annotation_area(row)))
            candidates[group].append((image_id, best))

    used_images: set[str] = set()
    for group in TARGET_GROUPS:
        ordered = sorted(
            candidates[group],
            key=lambda entry: hashlib.sha256(f"{group}:{entry[0]}".encode()).hexdigest(),
        )
        for image_id, primary in ordered:
            split = stable_split(image_id)
            if image_id in used_images or counts[group][split] >= SPLIT_QUOTAS[split]:
                continue
            selected[image_id] = {
                "group": group,
                "split": split,
                "primary": primary,
                "boxes": merge_overlapping(rows_by_image[image_id]),
            }
            counts[group][split] += 1
            used_images.add(image_id)
            if all(counts[name][part] >= SPLIT_QUOTAS[part] for name in TARGET_GROUPS for part in SPLIT_QUOTAS):
                break

    print(json.dumps(counts, indent=2))
    return selected


def save_record(image_id: str, record: dict, overwrite: bool) -> dict | None:
    downloaded = download_image(image_id)
    if not downloaded:
        return None
    image, source_url = downloaded
    split = record["split"]
    group = record["group"]
    stem = f"openimages_organic_{group}_{image_id}"
    crop = crop_box(image, record["primary"])
    if crop is None:
        return None

    classifier_path = CLASSIFIER / split / group / f"{stem}.jpg"
    raw_path = RAW_DATASET / split / group / f"{stem}.jpg"
    component_image = COMPONENTS / "images" / split / f"{stem}.jpg"
    component_label = COMPONENTS / "labels" / split / f"{stem}.txt"
    for path in (classifier_path, raw_path, component_image, component_label):
        path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite or not classifier_path.exists():
        crop.save(classifier_path, "JPEG", quality=92, optimize=True)
        shutil.copy2(classifier_path, raw_path)
        image.save(component_image, "JPEG", quality=90, optimize=True)
        lines = [
            f"1 {(float(row['XMin']) + float(row['XMax'])) / 2:.6f} "
            f"{(float(row['YMin']) + float(row['YMax'])) / 2:.6f} "
            f"{float(row['XMax']) - float(row['XMin']):.6f} "
            f"{float(row['YMax']) - float(row['YMin']):.6f}"
            for row in record["boxes"]
        ]
        component_label.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "image_id": image_id,
        "class": group,
        "split": split,
        "display_name": record["primary"]["display_name"],
        "source_url": source_url,
        "source": "Open Images V7 validation bounding boxes",
        "source_page": "https://storage.googleapis.com/openimages/web/index.html",
        "license": "Open Images source images are distributed under CC BY 2.0",
        "classifier_file": str(classifier_path.relative_to(ROOT)),
        "component_image": str(component_image.relative_to(ROOT)),
        "food_boxes": len(record["boxes"]),
    }


def write_component_config() -> None:
    lines = [
        f"path: {COMPONENTS}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
        "  0: closure",
        "  1: food",
        "  2: straw",
    ]
    (COMPONENTS / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    classes_path = CACHE / "classes.csv"
    boxes_path = CACHE / "validation.csv"
    download_metadata(CLASSES_URL, classes_path)
    download_metadata(BOXES_URL, boxes_path)

    display_by_mid = {row["LabelName"]: row["DisplayName"] for row in csv.DictReader(classes_path.open())}
    group_by_name = {name: group for group, names in TARGET_GROUPS.items() for name in names}
    rows_by_image: dict[str, list[dict[str, str]]] = defaultdict(list)
    with boxes_path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            display_name = display_by_mid.get(row["LabelName"])
            group = group_by_name.get(display_name or "")
            if not group or not usable(row):
                continue
            rows_by_image[row["ImageID"]].append({**row, "display_name": display_name, "target_group": group})

    selected = select_records(rows_by_image)
    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(save_record, image_id, record, args.overwrite): image_id
            for image_id, record in selected.items()
        }
        for index, future in enumerate(as_completed(futures), start=1):
            saved = future.result()
            if saved:
                records.append(saved)
            if index % 50 == 0 or index == len(futures):
                print(f"Downloaded {index}/{len(futures)}; kept {len(records)}", flush=True)

    records.sort(key=lambda row: (row["class"], row["split"], row["image_id"]))
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    write_component_config()
    print(f"Saved {len(records)} Organic examples and food-part annotations.")


if __name__ == "__main__":
    main()
