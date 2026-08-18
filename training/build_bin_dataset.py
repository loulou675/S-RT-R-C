"""Build a seven-class disposal-bin dataset from the item classifier dataset."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLASS_TO_BIN = {
    "aerosol_can": "hazardous",
    "aluminium_drink_can": "bottle_can",
    "battery": "hazardous",
    "cardboard_box": "paper_cardboard",
    "chemical_container": "hazardous",
    "dirty_plastic_bag": "landfill",
    "disposable_diaper": "landfill",
    "drink_carton": "paper_cardboard",
    "electronic_cable": "hazardous",
    "food_waste": "organic",
    "fruit_peel": "organic",
    "glass_drink_bottle": "bottle_can",
    "hair_clip": "landfill",
    "hair_tie": "landfill",
    "light_bulb": "hazardous",
    "medical_mask": "landfill",
    "medicine_blister_pack": "landfill",
    "mobile_phone": "hazardous",
    "newspaper": "paper_cardboard",
    "paper_bag": "paper_cardboard",
    "paper_cup": "landfill",
    "paper_plate": "landfill",
    "paperboard_packaging": "paper_cardboard",
    "pen_marker": "landfill",
    "phone_case": "landfill",
    "plastic_bag": "clean_plastic",
    "plastic_cosmetic_container": "clean_plastic",
    "plastic_cup_lid": "clean_plastic",
    "plastic_food_container": "clean_plastic",
    "plastic_takeaway_cup": "clean_plastic",
    "plastic_water_bottle": "bottle_can",
    "power_bank": "hazardous",
    "printing_paper": "paper_cardboard",
    "sanitary_pad": "landfill",
    "snack_wrapper": "clean_plastic",
    "steel_food_can": "bottle_can",
    "styrofoam_container": "clean_plastic",
    "tissue": "landfill",
    "unknown": "unknown",
    "vegetable_scraps": "organic",
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "training" / "classifier_dataset")
    parser.add_argument("--output", type=Path, default=ROOT / "training" / "bin_dataset")
    args = parser.parse_args()

    if args.output.exists():
        shutil.rmtree(args.output)

    counts: dict[tuple[str, str], int] = {}
    for split in ("train", "val", "test"):
        for item_dir in sorted(path for path in (args.source / split).iterdir() if path.is_dir()):
            bin_code = CLASS_TO_BIN.get(item_dir.name)
            if not bin_code:
                raise SystemExit(f"Missing bin mapping for {item_dir.name}")
            destination = args.output / split / bin_code
            destination.mkdir(parents=True, exist_ok=True)
            for index, image_path in enumerate(
                path for path in sorted(item_dir.iterdir()) if path.suffix.lower() in IMAGE_SUFFIXES
            ):
                target = destination / f"{item_dir.name}__{index:04d}{image_path.suffix.lower()}"
                os.link(image_path, target)
                counts[(split, bin_code)] = counts.get((split, bin_code), 0) + 1

    for split in ("train", "val", "test"):
        summary = ", ".join(
            f"{bin_code}={counts.get((split, bin_code), 0)}"
            for bin_code in sorted(set(CLASS_TO_BIN.values()))
        )
        print(f"{split}: {summary}")


if __name__ == "__main__":
    main()
