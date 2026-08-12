#!/usr/bin/env python3
"""Import selected Open Images household boxes as classifier crops and straw parts."""

from __future__ import annotations

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = Path("/tmp/sort-rac-openimages-household-yolo.zip")
CLASSIFIER_ROOT = ROOT / "training" / "dataset" / "train"
PARTS_ROOT = ROOT / "training" / "openimages_component_straw"
SOURCE_LOG = ROOT / "training" / "openimages-household-sources.jsonl"
SOURCE_PAGE = "https://www.kaggle.com/datasets/youssefelebiary/household-trash-recycling-dataset"

NAMES = [
    "Banana", "Apple", "Orange", "Tomato", "Carrot", "Cucumber", "Potato", "Bread", "Cake", "Pizza",
    "Hamburger", "Chicken", "Fish", "Food", "Tin can", "Bottle", "Facial tissue holder", "Toilet paper",
    "Paper towel", "Milk", "Snack", "Plastic bag", "Candy", "Light bulb", "Toothbrush", "Soap dispenser",
    "Drinking straw", "Fast food", "Pasta", "Pastry",
]

SOURCE_TO_APP = {
    "Tin can": "steel_food_can",
    "Bottle": "plastic_water_bottle",
    "Paper towel": "tissue",
    "Milk": "drink_carton",
    "Snack": "snack_wrapper",
    "Plastic bag": "plastic_bag",
    "Light bulb": "light_bulb",
}


def stable_split(stem: str) -> str:
    value = int(hashlib.sha256(f"oid-straw:{stem}".encode()).hexdigest()[:8], 16) % 100
    if value < 82:
        return "train"
    if value < 91:
        return "val"
    return "test"


def padded_crop(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image | None:
    cx, cy, width, height = box
    x1 = (cx - width / 2) * image.width
    y1 = (cy - height / 2) * image.height
    x2 = (cx + width / 2) * image.width
    y2 = (cy + height / 2) * image.height
    padding = 0.25 * max(x2 - x1, y2 - y1)
    left, top = max(0, round(x1 - padding)), max(0, round(y1 - padding))
    right, bottom = min(image.width, round(x2 + padding)), min(image.height, round(y2 + padding))
    if right - left < 64 or bottom - top < 64:
        return None
    return image.crop((left, top, right, bottom))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--per-class", type=int, default=180)
    args = parser.parse_args()

    classifier_counts = {name: 0 for name in SOURCE_TO_APP}
    part_counts = {"train": 0, "val": 0, "test": 0}
    seen_straw_images: set[str] = set()
    with ZipFile(args.archive) as archive, SOURCE_LOG.open("a", encoding="utf-8") as log:
        label_members = sorted(name for name in archive.namelist() if name.startswith("labels/") and name.endswith(".txt"))
        for label_member in label_members:
            split = Path(label_member).parts[1]
            stem = Path(label_member).stem
            image_member = f"images/{split}/{stem}.jpg"
            try:
                rows = []
                for line in archive.read(label_member).decode("utf-8").splitlines():
                    values = line.split()
                    if len(values) == 5:
                        rows.append((int(values[0]), tuple(float(value) for value in values[1:])))
                if not rows:
                    continue
                with Image.open(BytesIO(archive.read(image_member))) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
            except (KeyError, OSError, ValueError):
                continue

            for index, (class_id, box) in enumerate(rows):
                if not 0 <= class_id < len(NAMES):
                    continue
                source_class = NAMES[class_id]
                app_class = SOURCE_TO_APP.get(source_class)
                if app_class and classifier_counts[source_class] < args.per_class:
                    crop = padded_crop(image, box)
                    if crop is not None:
                        crop.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                        output = CLASSIFIER_ROOT / app_class / f"oid_household_{source_class.lower().replace(' ', '_')}_{stem}_{index}.jpg"
                        crop.save(output, "JPEG", quality=91, optimize=True)
                        classifier_counts[source_class] += 1
                        log.write(json.dumps({
                            "task": "classification_crop", "class": app_class, "source_class": source_class,
                            "source_image": image_member, "local_file": str(output.relative_to(ROOT)),
                            "dataset": "Household Trash Recycling Dataset / Open Images V7", "source_page": SOURCE_PAGE,
                            "license": "CC BY 4.0 (upstream Open Images provenance)",
                        }) + "\n")

            straw_rows = [(index, box) for index, (class_id, box) in enumerate(rows) if NAMES[class_id] == "Drinking straw"]
            if straw_rows and stem not in seen_straw_images:
                part_split = stable_split(stem)
                image_output = PARTS_ROOT / "images" / part_split / f"oid_{stem}.jpg"
                label_output = PARTS_ROOT / "labels" / part_split / f"oid_{stem}.txt"
                image_output.parent.mkdir(parents=True, exist_ok=True)
                label_output.parent.mkdir(parents=True, exist_ok=True)
                image.save(image_output, "JPEG", quality=92, optimize=True)
                label_output.write_text("\n".join(
                    f"0 {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}"
                    for _, (cx, cy, width, height) in straw_rows
                ) + "\n", encoding="utf-8")
                part_counts[part_split] += len(straw_rows)
                seen_straw_images.add(stem)
                log.write(json.dumps({
                    "task": "component_detection", "component": "straw", "source_image": image_member,
                    "local_image": str(image_output.relative_to(ROOT)), "boxes": len(straw_rows),
                    "dataset": "Household Trash Recycling Dataset / Open Images V7", "source_page": SOURCE_PAGE,
                    "license": "CC BY 4.0 (upstream Open Images provenance)",
                }) + "\n")

    yaml = [f"path: {PARTS_ROOT.resolve()}", "train: images/train", "val: images/val", "test: images/test", "names:", "  0: straw"]
    PARTS_ROOT.mkdir(parents=True, exist_ok=True)
    (PARTS_ROOT / "data.yaml").write_text("\n".join(yaml) + "\n", encoding="utf-8")
    print("Classifier crops:", classifier_counts)
    print("Straw boxes:", part_counts)


if __name__ == "__main__":
    main()
