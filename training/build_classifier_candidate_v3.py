#!/usr/bin/env python3
"""Build a source-balanced classifier candidate with a locked evaluation set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "training" / "dataset" / "train"
REFERENCE_ROOT = ROOT / "training" / "dataset_curated_v2"
DEFAULT_OUTPUT = ROOT / "training" / "dataset_curated_v3"
DEFAULT_MANIFEST = ROOT / "training" / "curated-split-v3.json"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".avif"}

# One bulk source must not dominate the visual style of a class. The less
# structured sources keep lower caps because their labels require more review.
SOURCE_LIMITS = {
    "rhw": 300,
    "commons": 120,
    "taco": 120,
    "hf": 100,
    "trashbox": 50,
    "trashnet": 80,
    "bdwaste": 40,
    "drinking_waste": 50,
    "oid_household": 160,
    "packwise": 140,
    "other": 100,
}
MAX_TRAIN_PER_CLASS = 420

# Open Images labels describe visible objects, not waste items. Only these
# mappings survived a contact-sheet review. In particular, Bottle, Milk and
# Snack are intentionally excluded because they mix materials or label food
# instead of its packaging.
REVIEWED_OID_PREFIXES = {
    "light_bulb": "oid_household_light_bulb_",
    "plastic_bag": "oid_household_plastic_bag_",
    "steel_food_can": "oid_household_tin_can_",
    "tissue": "oid_household_paper_towel_",
}

# PackWISE has instance boxes in difficult conveyor scenes. Keep only source
# categories whose meaning matches an app item closely enough for exact-item
# classification. Broader labels such as plastic-bottle and plastic-foil/bag
# are deliberately excluded.
REVIEWED_PACKWISE_PREFIXES = {
    "drink_carton": "packwise_beverage-carton_",
    "medicine_blister_pack": "packwise_blister_",
    "paper_cup": "packwise_paper-cup-pot_",
    "steel_food_can": "packwise_metal-can_",
    "styrofoam_container": "packwise_foamed-plastic_",
    "tissue": "packwise_tissue_",
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def difference_hash(path: Path) -> int:
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(image.getdata())
    bits = 0
    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]
            bits = (bits << 1) | int(left > right)
    return bits


def stable_key(path: Path) -> str:
    return hashlib.sha256(str(path.relative_to(ROOT)).encode()).hexdigest()


def source_stem(path: Path) -> str:
    return re.sub(r"^\d{4}_", "", path.stem)


def source_kind(path: Path) -> str:
    name = source_stem(path)
    if name.startswith("rhw_"):
        return "rhw"
    if name.startswith("commons_train_"):
        return "commons"
    if name.startswith("taco_"):
        return "taco"
    if name.startswith("hf_"):
        return "hf"
    if name.startswith("trashbox_"):
        return "trashbox"
    if name.startswith("trashnet_"):
        return "trashnet"
    if name.startswith("bdwaste_"):
        return "bdwaste"
    if name.startswith("drinking_waste_"):
        return "drinking_waste"
    if name.startswith("oid_household_"):
        return "oid_household"
    if name.startswith("packwise_"):
        return "packwise"
    return "other"


def candidate_is_reviewed(path: Path, class_name: str) -> bool:
    name = source_stem(path)
    if name.startswith("oid_household_"):
        allowed_prefix = REVIEWED_OID_PREFIXES.get(class_name)
        return allowed_prefix is not None and name.startswith(allowed_prefix)
    if name.startswith("packwise_"):
        allowed_prefix = REVIEWED_PACKWISE_PREFIXES.get(class_name)
        return allowed_prefix is not None and name.startswith(allowed_prefix)
    return True


def copy_as_jpeg(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
        image.save(destination, "JPEG", quality=91, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing candidate: {output}")

    classes = json.loads((ROOT / "training" / "classes.json").read_text(encoding="utf-8"))["classes"]
    eval_hashes: set[str] = set()
    eval_stems: set[str] = set()
    report: dict[str, dict[str, list[str]]] = {"train": {}, "val": {}, "test": {}}

    for split in ("val", "test"):
        for class_name in classes:
            report[split][class_name] = []
            source_dir = REFERENCE_ROOT / split / class_name
            for index, source in enumerate(sorted(source_dir.glob("*"))):
                if source.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                eval_hashes.add(file_hash(source))
                eval_stems.add(source_stem(source))
                destination = output / split / class_name / f"{index:04d}_{source_stem(source)}.jpg"
                copy_as_jpeg(source, destination)
                report[split][class_name].append(str(destination.relative_to(ROOT)))

    global_hashes = set(eval_hashes)
    skipped = defaultdict(int)
    for class_name in classes:
        candidates = [
            path
            for path in (SOURCE_ROOT / class_name).glob("*")
            if path.suffix.lower() in IMAGE_SUFFIXES
            and source_stem(path) not in eval_stems
            and not path.name.startswith("aug_")
            and candidate_is_reviewed(path, class_name)
        ]
        by_source: dict[str, list[Path]] = defaultdict(list)
        for path in sorted(candidates, key=stable_key):
            by_source[source_kind(path)].append(path)

        selected: list[Path] = []
        visual_hashes: list[int] = []
        for kind in sorted(by_source):
            accepted = 0
            for path in by_source[kind]:
                if accepted >= SOURCE_LIMITS[kind] or len(selected) >= MAX_TRAIN_PER_CLASS:
                    break
                try:
                    digest = file_hash(path)
                    visual = difference_hash(path)
                except Exception:
                    skipped["unreadable"] += 1
                    continue
                if digest in global_hashes:
                    skipped["exact_duplicate"] += 1
                    continue
                if any((visual ^ previous).bit_count() <= 2 for previous in visual_hashes):
                    skipped["near_duplicate"] += 1
                    continue
                global_hashes.add(digest)
                visual_hashes.append(visual)
                selected.append(path)
                accepted += 1

        report["train"][class_name] = []
        for index, source in enumerate(selected):
            destination = output / "train" / class_name / f"{index:04d}_{source.stem}.jpg"
            copy_as_jpeg(source, destination)
            report["train"][class_name].append(str(destination.relative_to(ROOT)))
        print(f"{class_name:<29} {len(selected):>4} originals")

    args.manifest.resolve().write_text(json.dumps({"splits": report, "skipped": dict(skipped)}, indent=2) + "\n")
    print("Skipped:", dict(skipped))
    print("Candidate:", output)


if __name__ == "__main__":
    main()
