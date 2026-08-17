#!/usr/bin/env python3
"""Collect diverse non-target object crops for the classifier's unknown class."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "training" / "classifier_dataset"
RAW_DATASET = ROOT / "training" / "dataset"
MANIFEST = ROOT / "training" / "source_manifests" / "openimages-unknown-sources.jsonl"
CACHE = Path("/tmp/sort-rac-openimages-unknown")
CLASSES_URL = "https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions-boxable.csv"
BOXES_URL = "https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv"
IMAGE_URL = "https://open-images-dataset.s3.amazonaws.com/validation/{image_id}.jpg"
USER_AGENT = "sort-rac-unknown-training/1.0"
PREFIX = "openimages_unknown_"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
EXCLUDED_IMAGE_IDS = {
    "11d783ff3dc27f6e",  # Mushroom-like crop conflicts with visible food.
    "1d2e07648ff74ba5",  # Strawberry crop conflicts with the Organic classes.
}

TARGET_GROUPS = {
    "people": {"Person", "Human face", "Human hand"},
    "furniture": {"Chair", "Table", "Desk", "Couch", "Bed"},
    "clothing": {"Clothing", "Footwear", "Handbag", "Hat"},
    "toys": {"Toy", "Doll", "Teddy bear", "Ball (Object)", "Balloon"},
    "plants": {"Houseplant", "Flower", "Tree"},
    "animals": {"Dog", "Cat", "Bird", "Horse"},
    "electronics": {"Laptop", "Computer keyboard", "Computer mouse", "Television", "Camera"},
    "transport": {"Bicycle", "Car", "Motorcycle"},
    "signage": {"Poster", "Billboard", "Traffic sign", "Clock"},
    "other": {"Scissors", "Musical instrument", "Guitar", "Piano", "Umbrella"},
}

# Reject source images explicitly annotated with one of the app's target families.
# The selected object is cropped as an additional safeguard against background noise.
FORBIDDEN_LABELS = {
    "Bottle",
    "Tin can",
    "Drink",
    "Drinking straw",
    "Coffee (drink)",
    "Coffee cup",
    "Food",
    "Fast food",
    "Seafood",
    "Fruit",
    "Vegetable",
    "Snack",
    "Plastic bag",
    "Paper towel",
    "Toilet paper",
    "Box",
    "Waste container",
    "Plate",
    "Light bulb",
    "Mobile phone",
    "Diaper",
    "Medical equipment",
}


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
    bucket = int(hashlib.sha256(f"unknown:{image_id}".encode()).hexdigest()[:8], 16) % 100
    if bucket < 76:
        return "train"
    if bucket < 88:
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
        and annotation_area(row) >= 0.02
    )


def crop_box(image: Image.Image, row: dict[str, str], padding: float = 0.18) -> Image.Image | None:
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
    if min(crop.size) < 112 or max(crop.size) / min(crop.size) > 4.5:
        return None
    return crop


def download_crop(candidate: dict) -> tuple[dict, Image.Image, str] | None:
    image_id = candidate["image_id"]
    source_url = IMAGE_URL.format(image_id=image_id)
    try:
        response = requests.get(source_url, headers={"User-Agent": USER_AGENT}, timeout=(10, 45))
        response.raise_for_status()
        image = ImageOps.exif_transpose(Image.open(BytesIO(response.content))).convert("RGB")
        crop = crop_box(image, candidate["row"])
        return (candidate, crop, source_url) if crop is not None else None
    except (requests.RequestException, UnidentifiedImageError, OSError):
        return None


def difference_hash(image: Image.Image) -> int:
    resized = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(resized.get_flattened_data())
    value = 0
    for y in range(8):
        for x in range(8):
            value = (value << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return value


def load_existing_hashes() -> list[int]:
    hashes: list[int] = []
    for split in ("train", "val", "test"):
        folder = CLASSIFIER / split / "unknown"
        if not folder.exists():
            continue
        for path in folder.iterdir():
            if path.name.startswith(PREFIX) or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            try:
                with Image.open(path) as image:
                    hashes.append(difference_hash(image))
            except (UnidentifiedImageError, OSError):
                continue
    return hashes


def near_duplicate(value: int, known: list[int], distance: int = 3) -> bool:
    return any((value ^ existing).bit_count() <= distance for existing in known)


def cleanup_generated() -> None:
    for base in (CLASSIFIER, RAW_DATASET):
        for split in ("train", "val", "test"):
            folder = base / split / "unknown"
            folder.mkdir(parents=True, exist_ok=True)
            for path in folder.glob(f"{PREFIX}*"):
                path.unlink()


def balanced_candidates(
    rows_by_group: dict[str, list[dict]],
    quotas: dict[str, int],
    overfetch: float,
) -> dict[tuple[str, str], list[dict]]:
    selected: dict[tuple[str, str], list[dict]] = {}
    used_images: set[str] = set()
    for group in TARGET_GROUPS:
        by_split_label: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for candidate in rows_by_group[group]:
            split = stable_split(candidate["image_id"])
            by_split_label[(split, candidate["display_name"])].append(candidate)
        for values in by_split_label.values():
            values.sort(key=lambda row: hashlib.sha256(f"{group}:{row['image_id']}".encode()).hexdigest())

        for split, quota in quotas.items():
            limit = max(quota, int(quota * overfetch))
            labels = sorted(TARGET_GROUPS[group])
            output: list[dict] = []
            max_bucket = max((len(by_split_label.get((split, label), [])) for label in labels), default=0)
            for offset in range(max_bucket):
                for label in labels:
                    bucket = by_split_label.get((split, label), [])
                    if offset >= len(bucket):
                        continue
                    candidate = bucket[offset]
                    if candidate["image_id"] not in used_images:
                        output.append(candidate)
                        used_images.add(candidate["image_id"])
                        if len(output) >= limit:
                            break
                if len(output) >= limit:
                    break
            selected[(group, split)] = output
    return selected


def save_crop(candidate: dict, crop: Image.Image, source_url: str) -> dict:
    group = candidate["group"]
    split = candidate["split"]
    image_id = candidate["image_id"]
    stem = f"{PREFIX}{group}_{image_id}"
    classifier_path = CLASSIFIER / split / "unknown" / f"{stem}.jpg"
    raw_path = RAW_DATASET / split / "unknown" / f"{stem}.jpg"
    crop.save(classifier_path, "JPEG", quality=92, optimize=True)
    shutil.copy2(classifier_path, raw_path)
    return {
        "image_id": image_id,
        "class": "unknown",
        "unknown_group": group,
        "split": split,
        "display_name": candidate["display_name"],
        "source_url": source_url,
        "source": "Open Images V7 validation bounding boxes",
        "source_page": "https://storage.googleapis.com/openimages/web/index.html",
        "license": "Open Images source images are distributed under CC BY 2.0",
        "classifier_file": str(classifier_path.relative_to(ROOT)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-per-group", type=int, default=50)
    parser.add_argument("--val-per-group", type=int, default=8)
    parser.add_argument("--test-per-group", type=int, default=8)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--overfetch", type=float, default=1.35)
    args = parser.parse_args()
    quotas = {"train": args.train_per_group, "val": args.val_per_group, "test": args.test_per_group}

    classes_path = CACHE / "classes.csv"
    boxes_path = CACHE / "validation.csv"
    download_metadata(CLASSES_URL, classes_path)
    download_metadata(BOXES_URL, boxes_path)
    display_by_mid = {
        row["LabelName"]: row["DisplayName"] for row in csv.DictReader(classes_path.open(encoding="utf-8"))
    }
    group_by_name = {name: group for group, names in TARGET_GROUPS.items() for name in names}
    blocked_images: set[str] = set()
    candidates_by_image_group: dict[tuple[str, str], dict] = {}

    with boxes_path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            display_name = display_by_mid.get(row["LabelName"])
            if display_name in FORBIDDEN_LABELS:
                blocked_images.add(row["ImageID"])
            group = group_by_name.get(display_name or "")
            if not group or not usable(row):
                continue
            key = (row["ImageID"], group)
            candidate = {
                "image_id": row["ImageID"],
                "group": group,
                "display_name": display_name,
                "row": row,
            }
            current = candidates_by_image_group.get(key)
            if current is None or annotation_area(row) > annotation_area(current["row"]):
                candidates_by_image_group[key] = candidate

    rows_by_group: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates_by_image_group.values():
        if candidate["image_id"] not in blocked_images and candidate["image_id"] not in EXCLUDED_IMAGE_IDS:
            rows_by_group[candidate["group"]].append(candidate)

    cleanup_generated()
    known_hashes = load_existing_hashes()
    buckets = balanced_candidates(rows_by_group, quotas, max(1.0, args.overfetch))
    records: list[dict] = []
    counts: dict[str, dict[str, int]] = {group: {split: 0 for split in quotas} for group in TARGET_GROUPS}

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        for (group, split), candidates in buckets.items():
            prepared = [{**candidate, "split": split} for candidate in candidates]
            for downloaded in executor.map(download_crop, prepared):
                if counts[group][split] >= quotas[split] or downloaded is None:
                    continue
                candidate, crop, source_url = downloaded
                image_hash = difference_hash(crop)
                if near_duplicate(image_hash, known_hashes):
                    continue
                known_hashes.append(image_hash)
                records.append(save_crop(candidate, crop, source_url))
                counts[group][split] += 1
            print(f"{group:<12} {split:<5} {counts[group][split]:>3}/{quotas[split]}", flush=True)

    records.sort(key=lambda row: (row["unknown_group"], row["split"], row["image_id"]))
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    print(f"Saved {len(records)} reviewed-by-rule unknown crops.")
    shortfalls = {
        f"{group}/{split}": quotas[split] - count
        for group, split_counts in counts.items()
        for split, count in split_counts.items()
        if count < quotas[split]
    }
    if shortfalls:
        print(f"Quota shortfalls: {json.dumps(shortfalls, sort_keys=True)}")


if __name__ == "__main__":
    main()
