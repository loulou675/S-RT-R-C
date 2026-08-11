"""Import a balanced train-only subset from a 30-class household dataset.

The source has 250 default and 250 real-world images for each source class.
Imported files are prefixed with ``rhw_`` so the split builder can keep this
bulk source out of validation and test. This prevents source-style leakage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/alistairking/recyclable-and-household-waste-classification"
SOURCE_PAGE = "https://www.kaggle.com/datasets/alistairking/recyclable-and-household-waste-classification"
DEFAULT_ARCHIVE = Path("/tmp/sort-rac-recyclable-household.zip")
DATASET_ROOT = ROOT / "training" / "dataset" / "train"
MANIFEST_PATH = ROOT / "training" / "recyclable-household-sources.jsonl"

SOURCE_TO_APP = {
    "aerosol_cans": "aerosol_can",
    "aluminum_food_cans": "steel_food_can",
    "aluminum_soda_cans": "aluminium_drink_can",
    "cardboard_boxes": "cardboard_box",
    "cardboard_packaging": "paperboard_packaging",
    "coffee_grounds": "food_waste",
    "eggshells": "food_waste",
    "food_waste": "food_waste",
    "glass_beverage_bottles": "glass_drink_bottle",
    "magazines": "newspaper",
    "newspaper": "newspaper",
    "office_paper": "printing_paper",
    "paper_cups": "paper_cup",
    "plastic_food_containers": "plastic_food_container",
    "plastic_shopping_bags": "plastic_bag",
    "plastic_soda_bottles": "plastic_water_bottle",
    "plastic_trash_bags": "plastic_bag",
    "plastic_water_bottles": "plastic_water_bottle",
    "steel_food_cans": "steel_food_can",
    "styrofoam_cups": "styrofoam_container",
    "styrofoam_food_containers": "styrofoam_container",
    "tea_bags": "food_waste",
    # Useful out-of-taxonomy negatives for rejection training.
    "clothing": "unknown",
    "disposable_plastic_cutlery": "unknown",
    "glass_cosmetic_containers": "unknown",
    "glass_food_jars": "unknown",
    "plastic_cup_lids": "unknown",
    "plastic_detergent_bottles": "unknown",
    "plastic_straws": "unknown",
    "shoes": "unknown",
}


def download_archive(path: Path) -> None:
    if path.exists() and path.stat().st_size > 500_000_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(DOWNLOAD_URL, stream=True, timeout=(20, 180)) as response:
        response.raise_for_status()
        with path.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                output.write(chunk)


def stable_sample(names: list[str], count: int) -> list[str]:
    return sorted(names, key=lambda name: hashlib.sha256(name.encode()).hexdigest())[:count]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--per-source", type=int, default=60)
    args = parser.parse_args()
    download_archive(args.archive)

    existing = set()
    if MANIFEST_PATH.exists():
        existing = {
            json.loads(line).get("source_file")
            for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    with ZipFile(args.archive) as archive, MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
        added_by_class: dict[str, int] = {}
        for source_class, app_class in SOURCE_TO_APP.items():
            candidates = [
                name for name in archive.namelist()
                if name.startswith(f"images/images/{source_class}/")
                and name.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                and name not in existing
            ]
            default = [name for name in candidates if "/default/" in name]
            real_world = [name for name in candidates if "/real_world/" in name]
            half = max(1, args.per_source // 2)
            selected = stable_sample(default, half) + stable_sample(real_world, args.per_source - half)
            destination = DATASET_ROOT / app_class
            destination.mkdir(parents=True, exist_ok=True)
            added = 0
            for source_file in selected:
                try:
                    with Image.open(BytesIO(archive.read(source_file))) as opened:
                        image = ImageOps.exif_transpose(opened).convert("RGB")
                except Exception:
                    continue
                source_kind = "real" if "/real_world/" in source_file else "default"
                digest = hashlib.sha256(source_file.encode()).hexdigest()[:12]
                output = destination / f"rhw_{source_class}_{source_kind}_{digest}.jpg"
                image.save(output, "JPEG", quality=90, optimize=True)
                manifest.write(json.dumps({
                    "class": app_class,
                    "source_class": source_class,
                    "source_file": source_file,
                    "local_file": str(output.relative_to(ROOT)),
                    "dataset": "Recyclable and Household Waste Classification",
                    "source_page": SOURCE_PAGE,
                    "license": "MIT",
                    "split_hint": "train_only_bulk_source",
                    "review_status": "mapped_source_class",
                }) + "\n")
                manifest.flush()
                existing.add(source_file)
                added += 1
            added_by_class[app_class] = added_by_class.get(app_class, 0) + added
            print(f"{source_class} -> {app_class}: added {added}", flush=True)

    print("\nAdded by app class:")
    for class_name, count in sorted(added_by_class.items()):
        print(f"  {class_name}: {count}")


if __name__ == "__main__":
    main()
