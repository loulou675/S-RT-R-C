"""Normalize the hand-sorted real-image folder into the classifier dataset."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "real image"
DATASET = ROOT / "training" / "classifier_dataset"
MANIFEST = ROOT / "training" / "source_manifests" / "real-image-import.jsonl"
CLASSES = json.loads((ROOT / "training" / "classes.json").read_text(encoding="utf-8"))["classes"]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}

SOURCE_TO_CLASS = {
    "Bottle & Can_/aluminium_drink_can": "aluminium_drink_can",
    "Bottle & Can_/steel_food_can": "steel_food_can",
    "Clean Plastic/Plastic_lid": "plastic_cup_lid",
    "Clean Plastic/bubble_wrap": "unknown",
    "Clean Plastic/plastic_bag": "plastic_bag",
    "Clean Plastic/plastic_cosmetic_container ": "plastic_cosmetic_container",
    "Clean Plastic/plastic_food_container": "plastic_food_container",
    "Landfill_/Dirty_plastic": "dirty_plastic_bag",
    "Landfill_/birthday_candle": "unknown",
    "Landfill_/clothing_foam_padding": "unknown",
    "Landfill_/fabric": "unknown",
    "Landfill_/medical_mask": "medical_mask",
    "Landfill_/medicine_blister_pack": "medicine_blister_pack",
    "Landfill_/paper_plate": "paper_plate",
    "Landfill_/tissue": "tissue",
    "Organic_/food_waste": "food_waste",
    "Organic_/fruit_peel": "fruit_peel",
    "Paper & Cardboard/Greyboard": "paperboard_packaging",
    "Paper & Cardboard/Paper_food_container": "paperboard_packaging",
    "Paper & Cardboard/cardboard_box": "cardboard_box",
    "Paper & Cardboard/paper_bag": "paper_bag",
    "Paper & Cardboard/paperboard_packaging": "paperboard_packaging",
    "Special Handling/power_adapter": "unknown",
    "Unknown": "unknown",
}


def classify_source(path: Path, configured_class: str) -> tuple[str, str]:
    relative_parent = path.parent.relative_to(SOURCE).as_posix()
    stem_number = int(path.stem.removeprefix("IMG_")) if path.stem.startswith("IMG_") and path.stem[4:].isdigit() else None

    if relative_parent == "Landfill_/Dirty_plastic":
        if stem_number is not None and stem_number <= 9060:
            return "unknown", "train"
        if stem_number is not None and stem_number >= 9170:
            return configured_class, "test"
        return configured_class, "val" if stem_number is not None and stem_number >= 9153 else "train"

    if relative_parent == "Clean Plastic/plastic_cosmetic_container ":
        if stem_number is not None and stem_number >= 8620:
            return configured_class, "test"
        return configured_class, "val" if stem_number is not None and stem_number >= 8599 else "train"

    return configured_class, "train"


def open_image(path: Path) -> Image.Image:
    if path.suffix.lower() not in {".heic", ".heif"}:
        with Image.open(path) as image:
            return ImageOps.exif_transpose(image).convert("RGB")

    with tempfile.TemporaryDirectory(prefix="sort-rac-heic-") as directory:
        converted = Path(directory) / f"{path.stem}.jpg"
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(path), "--out", str(converted)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with Image.open(converted) as image:
            return ImageOps.exif_transpose(image).convert("RGB")


def save_normalized(path: Path, target_class: str, split: str) -> tuple[Path, str]:
    image = open_image(path)
    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)

    with tempfile.NamedTemporaryFile(suffix=".jpg") as handle:
        image.save(handle.name, "JPEG", quality=90, optimize=True)
        payload = Path(handle.name).read_bytes()

    digest = hashlib.sha256(payload).hexdigest()
    destination = DATASET / split / target_class / f"real_{target_class}_{digest[:16]}.jpg"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(payload)
    return destination, digest


def relabel_existing_lids(records: list[dict[str, object]]) -> None:
    unknown = DATASET / "train" / "unknown"
    if not unknown.exists():
        return

    candidates = sorted(path for path in unknown.iterdir() if "plastic_cup_lids" in path.name)
    for path in candidates:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        split = "val" if int(digest[:2], 16) < 51 else "train"
        destination = DATASET / split / "plastic_cup_lid" / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            path.unlink()
        else:
            shutil.move(path, destination)

    current = []
    for split in ("train", "val", "test"):
        current.extend((path, split) for path in (DATASET / split / "plastic_cup_lid").glob("*plastic_cup_lids*"))
    for path, old_split in current:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        bucket = int(digest[:2], 16)
        split = "test" if bucket < 26 else "val" if bucket < 64 else "train"
        destination = DATASET / split / "plastic_cup_lid" / path.name
        if path != destination:
            if destination.exists():
                path.unlink()
            else:
                shutil.move(path, destination)

    for split in ("train", "val", "test"):
        directory = DATASET / split / "plastic_cup_lid"
        for path in sorted(directory.glob("*plastic_cup_lids*")):
            records.append(
                {
                    "source": "Recyclable Household Waste/plastic_cup_lids",
                    "destination": str(path.relative_to(ROOT)),
                    "class": "plastic_cup_lid",
                    "split": split,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "note": "Corrected a previously conservative unknown mapping.",
                }
            )


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Missing source folder: {SOURCE}")

    for split in ("train", "val", "test"):
        for class_name in CLASSES:
            (DATASET / split / class_name).mkdir(parents=True, exist_ok=True)
        for path in (DATASET / split).glob("*/real_*.jpg"):
            path.unlink()

    records: list[dict[str, object]] = []
    skipped: list[str] = []
    for relative_parent, configured_class in SOURCE_TO_CLASS.items():
        directory = SOURCE / relative_parent
        if not directory.exists():
            continue
        for path in sorted(candidate for candidate in directory.iterdir() if candidate.is_file()):
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                skipped.append(str(path.relative_to(ROOT)))
                continue
            target_class, split = classify_source(path, configured_class)
            destination, digest = save_normalized(path, target_class, split)
            records.append(
                {
                    "source": str(path.relative_to(ROOT)),
                    "destination": str(destination.relative_to(ROOT)),
                    "class": target_class,
                    "split": split,
                    "sha256": digest,
                }
            )

    relabel_existing_lids(records)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")

    counts: dict[tuple[str, str], int] = {}
    for record in records:
        key = (str(record["split"]), str(record["class"]))
        counts[key] = counts.get(key, 0) + 1
    for (split, class_name), count in sorted(counts.items()):
        print(f"{split:<5} {class_name:<28} {count:>4}")
    print(f"\nImported {len(records)} images. Skipped {len(skipped)} non-image files.")
    for path in skipped:
        print(f"Skipped: {path}")
    print(f"Manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
