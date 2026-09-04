"""Add licensed Open Images drinking-straw boxes to the component dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "training" / "component_dataset"
MANIFEST = ROOT / "training" / "source_manifests" / "openimages-straw-sources.jsonl"
CACHE = Path("/tmp/sort-rac-openimages-straw")
CLASSES_URL = "https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions-boxable.csv"
BOXES_URL = "https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv"
IMAGE_URL = "https://open-images-dataset.s3.amazonaws.com/validation/{image_id}.jpg"
USER_AGENT = "sort-rac-component-training/1.0"
PREFIX = "openimages_straw_"
QUOTAS = {"train": 55, "val": 12, "test": 12}


def download(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 1000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=180, stream=True) as response:
        response.raise_for_status()
        with path.open("wb") as target:
            for chunk in response.iter_content(1024 * 1024):
                target.write(chunk)


def stable_split(image_id: str) -> str:
    bucket = int(hashlib.sha256(f"straw:{image_id}".encode()).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "val"
    return "test"


def usable(row: dict[str, str]) -> bool:
    width = float(row["XMax"]) - float(row["XMin"])
    height = float(row["YMax"]) - float(row["YMin"])
    return (
        row.get("IsDepiction") != "1"
        and row.get("IsInside") != "1"
        and row.get("IsGroupOf") != "1"
        and width > 0.015
        and height > 0.04
        and width * height >= 0.002
    )


def cleanup() -> None:
    for split in QUOTAS:
        for folder in (DATASET / "images" / split, DATASET / "labels" / split):
            folder.mkdir(parents=True, exist_ok=True)
            for path in folder.glob(f"{PREFIX}*"):
                path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    classes_path = CACHE / "classes.csv"
    boxes_path = CACHE / "validation-boxes.csv"
    download(CLASSES_URL, classes_path)
    download(BOXES_URL, boxes_path)

    with classes_path.open(encoding="utf-8") as source:
        labels = {display: label for label, display in csv.reader(source)}
    label_id = labels.get("Drinking straw")
    if not label_id:
        raise SystemExit("Open Images label 'Drinking straw' was not found")

    boxes: dict[str, list[dict[str, str]]] = defaultdict(list)
    with boxes_path.open(encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row["LabelName"] == label_id and usable(row):
                boxes[row["ImageID"]].append(row)

    selected: dict[str, list[str]] = {split: [] for split in QUOTAS}
    for image_id in sorted(boxes, key=lambda value: hashlib.sha256(value.encode()).hexdigest()):
        split = stable_split(image_id)
        if len(selected[split]) < QUOTAS[split]:
            selected[split].append(image_id)
    if any(len(selected[split]) < quota for split, quota in QUOTAS.items()):
        # The validation subset currently contains only a handful of reviewed
        # straw boxes. Keep image IDs independent and reserve one for each
        # evaluation split instead of silently training on all of them.
        ordered = sorted(boxes, key=lambda value: hashlib.sha256(value.encode()).hexdigest())
        if len(ordered) < 3:
            raise SystemExit(f"Not enough independent straw images: {len(ordered)}")
        selected = {"train": ordered[:-2], "val": [ordered[-2]], "test": [ordered[-1]]}

    cleanup()
    records: list[dict[str, object]] = []
    for split, image_ids in selected.items():
        for image_id in image_ids:
            url = IMAGE_URL.format(image_id=image_id)
            try:
                response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(10, 60))
                response.raise_for_status()
                image = ImageOps.exif_transpose(Image.open(BytesIO(response.content))).convert("RGB")
            except (requests.RequestException, UnidentifiedImageError, OSError):
                continue
            if min(image.size) < 200:
                continue
            image_path = DATASET / "images" / split / f"{PREFIX}{image_id}.jpg"
            label_path = DATASET / "labels" / split / f"{PREFIX}{image_id}.txt"
            if args.overwrite or not image_path.exists():
                image.save(image_path, "JPEG", quality=90, optimize=True)
                lines = []
                for row in boxes[image_id]:
                    x1, x2 = float(row["XMin"]), float(row["XMax"])
                    y1, y2 = float(row["YMin"]), float(row["YMax"])
                    lines.append(f"2 {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}")
                label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            records.append(
                {
                    "imageId": image_id,
                    "split": split,
                    "boxes": len(boxes[image_id]),
                    "sourceImage": url,
                    "source": "Open Images V7 validation images and V5 bounding boxes",
                    "sourcePage": "https://storage.googleapis.com/openimages/web/index.html",
                    "license": "CC BY 2.0",
                }
            )

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    counts = {split: sum(record["split"] == split for record in records) for split in QUOTAS}
    print(f"Imported drinking-straw images: {counts}")
    print(f"Manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
