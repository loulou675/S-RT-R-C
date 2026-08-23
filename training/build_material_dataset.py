"""Build a seven-class material dataset from the preserved v66 item splits."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ITEM_TO_MATERIAL = {
    "aerosol_can": "metal",
    "aluminium_drink_can": "metal",
    "battery": "electronic_battery",
    "cardboard_box": "paper_cardboard",
    "chemical_container": "plastic",
    "dirty_plastic_bag": "plastic",
    "disposable_cutlery": "plastic",
    "disposable_diaper": "mixed_uncertain",
    "drink_carton": "paper_cardboard",
    "electronic_cable": "electronic_battery",
    "food_waste": "organic",
    "fruit_peel": "organic",
    "glass_drink_bottle": "glass",
    "hair_clip": "mixed_uncertain",
    "hair_tie": "mixed_uncertain",
    "light_bulb": "electronic_battery",
    "medical_mask": "mixed_uncertain",
    "medicine_blister_pack": "mixed_uncertain",
    "mobile_phone": "electronic_battery",
    "newspaper": "paper_cardboard",
    "paper_bag": "paper_cardboard",
    "paper_cup": "paper_cardboard",
    "paper_plate": "paper_cardboard",
    "paperboard_packaging": "paper_cardboard",
    "pen_marker": "mixed_uncertain",
    "phone_case": "plastic",
    "plastic_bag": "plastic",
    "plastic_cosmetic_container": "plastic",
    "plastic_cup_lid": "plastic",
    "plastic_food_container": "plastic",
    "plastic_takeaway_cup": "plastic",
    "plastic_water_bottle": "plastic",
    "power_bank": "electronic_battery",
    "printing_paper": "paper_cardboard",
    "sanitary_pad": "mixed_uncertain",
    "snack_wrapper": "plastic",
    "steel_food_can": "metal",
    "styrofoam_container": "plastic",
    "tissue": "paper_cardboard",
    "unknown": "mixed_uncertain",
    "vegetable_scraps": "organic",
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "training" / "material_dataset")
    parser.add_argument("--minimum-train-images", type=int, default=800)
    args = parser.parse_args()

    if args.output.exists():
        shutil.rmtree(args.output)

    counts: dict[tuple[str, str], int] = {}
    for split in ("train", "val", "test"):
        source_split = args.source / split
        source_classes = sorted(path for path in source_split.iterdir() if path.is_dir())
        missing = [path.name for path in source_classes if path.name not in ITEM_TO_MATERIAL]
        if missing:
            raise SystemExit(f"Missing material mapping for: {', '.join(missing)}")

        for item_dir in source_classes:
            material_code = ITEM_TO_MATERIAL[item_dir.name]
            destination = args.output / split / material_code
            destination.mkdir(parents=True, exist_ok=True)
            for index, image_path in enumerate(
                path for path in sorted(item_dir.iterdir()) if path.suffix.lower() in IMAGE_SUFFIXES
            ):
                target = destination / f"{item_dir.name}__{index:04d}{image_path.suffix.lower()}"
                try:
                    os.link(image_path, target)
                except OSError:
                    shutil.copy2(image_path, target)
                counts[(split, material_code)] = counts.get((split, material_code), 0) + 1

    material_codes = sorted(set(ITEM_TO_MATERIAL.values()))
    for material_code in material_codes:
        current = counts.get(("train", material_code), 0)
        if current >= args.minimum_train_images:
            continue
        destination = args.output / "train" / material_code
        originals = sorted(path for path in destination.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
        for index in range(args.minimum_train_images - current):
            source = originals[index % len(originals)]
            target = destination / f"oversample__{index:04d}__{source.name}"
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
        counts[("train", material_code)] = args.minimum_train_images

    for split in ("train", "val", "test"):
        summary = ", ".join(
            f"{material_code}={counts.get((split, material_code), 0)}"
            for material_code in material_codes
        )
        print(f"{split}: {summary}")


if __name__ == "__main__":
    main()
