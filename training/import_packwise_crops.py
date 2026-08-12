#!/usr/bin/env python3
"""Import reviewed object crops from the PackWISE COCO archive.

PackWISE scenes contain many objects on a conveyor. Classification training
needs one item per image, so this importer uses the human-labelled boxes and
adds context padding around each instance. Only the original train split is
eligible for the classifier pool; PackWISE val/test remain untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = Path("/tmp/PackWISE_dataset_v2.zip")
OUTPUT_ROOT = ROOT / "training" / "dataset" / "train"
MANIFEST = ROOT / "training" / "packwise-sources.jsonl"

CATEGORY_MAP = {
    "plastic-foil/bag": "plastic_bag",
    "paper-bag": "paper_bag",
    "beverage-carton": "drink_carton",
    "plastic-cup/pot": "plastic_takeaway_cup",
    "blister": "medicine_blister_pack",
    "metal-can": "steel_food_can",
    "tissue": "tissue",
    "foamed-plastic": "styrofoam_container",
    "plastic-bottle": "plastic_water_bottle",
    "paper-cup/pot": "paper_cup",
}


def stable_order(annotation: dict) -> str:
    return hashlib.sha256(f"packwise:{annotation['id']}".encode()).hexdigest()


def crop_with_context(image: Image.Image, bbox: list[float], padding: float = 0.22) -> Image.Image:
    x, y, width, height = bbox
    side = max(width, height) * (1 + padding * 2)
    center_x, center_y = x + width / 2, y + height / 2
    left = max(0, center_x - side / 2)
    top = max(0, center_y - side / 2)
    right = min(image.width, center_x + side / 2)
    bottom = min(image.height, center_y + side / 2)
    return image.crop((left, top, right, bottom))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--per-class", type=int, default=160)
    parser.add_argument("--minimum-area", type=int, default=12_000)
    args = parser.parse_args()

    counts: Counter[str] = Counter()
    records: list[dict] = []
    with zipfile.ZipFile(args.archive) as archive:
        coco = json.loads(archive.read("data/train.json"))
        categories = {entry["id"]: entry["name"] for entry in coco["categories"]}
        images = {entry["id"]: entry for entry in coco["images"]}
        by_image: dict[int, list[dict]] = defaultdict(list)
        for annotation in sorted(coco["annotations"], key=stable_order):
            category = categories.get(annotation["category_id"])
            target = CATEGORY_MAP.get(category)
            if not target or counts[target] >= args.per_class:
                continue
            if annotation.get("area", 0) < args.minimum_area or annotation.get("iscrowd", 0):
                continue
            by_image[annotation["image_id"]].append(annotation)

        for image_id, annotations in by_image.items():
            metadata = images[image_id]
            member = f"data/train/{metadata['file_name']}"
            with Image.open(io.BytesIO(archive.read(member))) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                for annotation in annotations:
                    category = categories[annotation["category_id"]]
                    target = CATEGORY_MAP[category]
                    if counts[target] >= args.per_class:
                        continue
                    crop = crop_with_context(image, annotation["bbox"])
                    if min(crop.size) < 64:
                        continue
                    crop.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                    digest = hashlib.sha256(f"{image_id}:{annotation['id']}".encode()).hexdigest()[:16]
                    destination = OUTPUT_ROOT / target / f"packwise_{category.replace('/', '-')}_{digest}.jpg"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    crop.save(destination, "JPEG", quality=91, optimize=True)
                    counts[target] += 1
                    records.append({
                        "source": "PackWISE v2",
                        "license": "CC BY 4.0",
                        "source_url": "https://fordatis.fraunhofer.de/handle/fordatis/463.2",
                        "source_split": "train",
                        "source_image": metadata["file_name"],
                        "annotation_id": annotation["id"],
                        "source_category": category,
                        "class": target,
                        "local_file": str(destination.relative_to(ROOT)),
                    })

    MANIFEST.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    for target, count in sorted(counts.items()):
        print(f"{target:<29} {count:>4}")
    print(f"Imported {sum(counts.values())} reviewed-box crops")


if __name__ == "__main__":
    main()
