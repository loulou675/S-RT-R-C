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
CONDITION_DATASET = ROOT / "training" / "condition_dataset"
MANIFEST = ROOT / "training" / "source_manifests" / "real-image-import.jsonl"
CLASSES = json.loads((ROOT / "training" / "classes.json").read_text(encoding="utf-8"))["classes"]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

# Explicit object-level holdouts for the newly photographed classes. These are
# separate physical objects, not alternate views of an object used for train.
OBJECT_SPLIT_OVERRIDES = {
    "broken_black_clips_session_d": "val",
    "assorted_clips_session_f": "test",
    "black_hair_tie_session_a": "train",
    "white_scrunchie_session_b": "val",
    "plush_hair_tie_session_c": "test",
    **{f"pen_{index:02d}": "train" for index in range(1, 7)},
    **{f"pen_{index:02d}": "val" for index in range(7, 9)},
    **{f"pen_{index:02d}": "test" for index in range(9, 11)},
    "phone_case_session_a": "train",
}

SOURCE_TO_CLASS = {
    "Bottle & Can_/aluminium_drink_can": "aluminium_drink_can",
    "Bottle & Can_/glass_drink_bottle": "glass_drink_bottle",
    "Bottle & Can_/plastic_water_bottle": "plastic_water_bottle",
    "Bottle & Can_/steel_food_can": "steel_food_can",
    "Clean Plastic/Plastic_lid": "plastic_cup_lid",
    "Clean Plastic/bubble_wrap": "unknown",
    "Clean Plastic/plastic_bag": "plastic_bag",
    "Clean Plastic/plastic_cosmetic_container ": "plastic_cosmetic_container",
    "Clean Plastic/plastic_food_container": "plastic_food_container",
    "Clean Plastic/plastic_takeaway_cup": "plastic_takeaway_cup",
    "Clean Plastic/snack_wrapper": "snack_wrapper",
    "Clean Plastic/styrofoam_container": "styrofoam_container",
    "Landfill_/Dirty_plastic": "dirty_plastic_bag",
    "Landfill_/birthday_candle": "unknown",
    "Landfill_/clothing_foam_padding": "unknown",
    "Landfill_/fabric": "unknown",
    "Landfill_/hair_clip": "hair_clip",
    "Landfill_/hair_tie": "hair_tie",
    "Landfill_/medical_mask": "medical_mask",
    "Landfill_/medicine_blister_pack": "medicine_blister_pack",
    "Landfill_/paper_cup": "paper_cup",
    "Landfill_/paper_plate": "paper_plate",
    "Landfill_/pen_marker": "pen_marker",
    "Landfill_/phone_case": "phone_case",
    "Landfill_/sanitary_pad": "sanitary_pad",
    "Landfill_/tissue": "tissue",
    "Organic_/food_waste": "food_waste",
    "Organic_/fruit_peel": "fruit_peel",
    "Organic_/vegetable_scraps": "vegetable_scraps",
    "Paper & Cardboard/Greyboard": "paperboard_packaging",
    "Paper & Cardboard/Paper_food_container": "paperboard_packaging",
    "Paper & Cardboard/cardboard_box": "cardboard_box",
    "Paper & Cardboard/drink_carton": "drink_carton",
    "Paper & Cardboard/newspaper`": "newspaper",
    "Paper & Cardboard/paper_bag": "paper_bag",
    "Paper & Cardboard/paperboard_packaging": "paperboard_packaging",
    "Paper & Cardboard/printing_paper": "printing_paper",
    "Special Handling/aerosol_can": "aerosol_can",
    "Special Handling/battery": "battery",
    "Special Handling/power_adapter": "unknown",
    "Unknown": "unknown",
}


def object_group_from_path(path: Path) -> str | None:
    if path.stem.startswith("obj_") and "__" in path.stem:
        return path.stem.split("__", 1)[0].removeprefix("obj_")
    return None


def visible_condition_from_path(path: Path, group: str | None) -> str | None:
    aliases = {
        "clean": "clean_empty",
        "clean_empty": "clean_empty",
        "clean_empty_with_lid": "clean_empty",
        "dirty": "dirty_residue",
        "dirty_residue": "dirty_residue",
        "used": "used",
    }
    for token in path.stem.split("__")[1:]:
        if token in aliases:
            return aliases[token]
    if group:
        for prefix, condition in aliases.items():
            if group.startswith(f"{prefix}_"):
                return condition
    return None


def classify_source(path: Path, configured_class: str) -> tuple[str, str]:
    relative_parent = path.parent.relative_to(SOURCE).as_posix()
    object_group = object_group_from_path(path)
    if object_group:
        if object_group in OBJECT_SPLIT_OVERRIDES:
            return configured_class, OBJECT_SPLIT_OVERRIDES[object_group]
        bucket = int(hashlib.sha256(object_group.encode("utf-8")).hexdigest()[:8], 16) % 100
        split = "train" if bucket < 70 else "val" if bucket < 85 else "test"
        return configured_class, split

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
        try:
            with Image.open(converted) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
        except OSError:
            # Some recent iPhone HEIC files produce a JPEG that sips reports as
            # successful but Pillow cannot decode. ffmpeg handles those files.
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(path), "-frames:v", "1", str(converted)],
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
        current.extend(
            (path, split)
            for path in (DATASET / split / "plastic_cup_lid").glob("*plastic_cup_lids*")
            if not path.name.startswith("oversample_")
        )
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
            if path.name.startswith("oversample_"):
                continue
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
        for pattern in ("*/real_*.jpg", "*/oversample_*"):
            for path in (DATASET / split).glob(pattern):
                path.unlink()
        for condition in ("clean_empty", "dirty_residue"):
            directory = CONDITION_DATASET / split / condition
            directory.mkdir(parents=True, exist_ok=True)
            for path in directory.glob("real_condition_*.jpg"):
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
            object_group = object_group_from_path(path)
            visible_condition = visible_condition_from_path(path, object_group)
            condition_destination = None
            if visible_condition in {"clean_empty", "dirty_residue"}:
                condition_destination = (
                    CONDITION_DATASET
                    / split
                    / visible_condition
                    / f"real_condition_{digest[:16]}.jpg"
                )
                shutil.copy2(destination, condition_destination)
            records.append(
                {
                    "source": str(path.relative_to(ROOT)),
                    "destination": str(destination.relative_to(ROOT)),
                    "class": target_class,
                    "split": split,
                    "sha256": digest,
                    "objectGroup": object_group,
                    "visibleCondition": visible_condition,
                    "conditionDestination": (
                        str(condition_destination.relative_to(ROOT)) if condition_destination else None
                    ),
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
