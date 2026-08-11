"""Build reproducible train/validation/test folders from reviewed images."""

from __future__ import annotations

import hashlib
import json
import shutil
import argparse
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "training" / "dataset"
DEFAULT_OUTPUT_ROOT = ROOT / "training" / "dataset_curated"
DEFAULT_MANIFEST_PATH = ROOT / "training" / "curated-split.json"
CLASSES = json.loads((ROOT / "training" / "classes.json").read_text(encoding="utf-8"))["classes"]
MAX_INDEPENDENT_ORIGINALS_PER_CLASS = 80
MAX_TRAIN_ONLY_SOURCE_IMAGES_PER_CLASS = 120
TRAIN_ONLY_PREFIXES = ("rhw_", "drinking_waste_cc0_", "commons_train_", "taco_field_")

EXCLUDE = {
    "training/dataset/val/fruit_peel/000468_6e8b938e5d0641cd891f239a3a969d12~mv2.jpeg",
    "training/dataset/test/fruit_peel/8346e604-2702-48c6-becd-21e1987ec0e6_julia-kuzenkov-TjFetPc6NXs-unsplash.avif",
    "training/dataset/test/battery/LR03XWA-2SB_SPL.webp",
}


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stable_key(path: Path) -> str:
    return hashlib.sha256(str(path.relative_to(ROOT)).encode()).hexdigest()


def difference_hash(path: Path) -> int:
    """Return a small visual fingerprint used to reject near-duplicate photos."""
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


def split_files(files: list[Path]) -> dict[str, list[Path]]:
    ordered = sorted(files, key=stable_key)
    count = len(ordered)
    if count == 1:
        return {"train": ordered, "val": [], "test": []}
    if count == 2:
        return {"train": ordered[:1], "val": ordered[1:], "test": []}

    val_count = max(1, round(count * 0.15))
    test_count = max(1, round(count * 0.15))
    return {
        "train": ordered[: count - val_count - test_count],
        "val": ordered[count - val_count - test_count : count - test_count],
        "test": ordered[count - test_count :],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()
    output_root = args.output.resolve()
    manifest_path = args.manifest.resolve()

    if output_root.exists():
        raise SystemExit(f"Refusing to overwrite existing curated dataset: {output_root}")

    for split in ("train", "val", "test"):
        for class_name in CLASSES:
            (output_root / split / class_name).mkdir(parents=True, exist_ok=True)

    seen_hashes: set[str] = set()
    manifest: dict[str, dict[str, list[str]]] = {split: {} for split in ("train", "val", "test")}

    for class_name in CLASSES:
        candidates = []
        for source_split in ("train", "val", "test"):
            source_folder = SOURCE_ROOT / source_split / class_name
            if not source_folder.exists():
                continue
            candidates.extend(
                path
                for path in source_folder.iterdir()
                if path.is_file() and path.name not in {".gitkeep", ".DS_Store"} and str(path.relative_to(ROOT)) not in EXCLUDE
            )

        unique_files = []
        visual_hashes: list[int] = []
        for path in sorted(candidates):
            file_hash = digest(path)
            if file_hash in seen_hashes:
                continue
            try:
                visual_hash = difference_hash(path)
            except Exception as error:  # noqa: BLE001 - report and skip unreadable candidates
                print(f"skip unreadable {path.relative_to(ROOT)}: {type(error).__name__}")
                continue
            if any((visual_hash ^ previous).bit_count() <= 3 for previous in visual_hashes):
                print(f"skip near-duplicate {path.relative_to(ROOT)}")
                continue
            seen_hashes.add(file_hash)
            visual_hashes.append(visual_hash)
            unique_files.append(path)

        # Bulk datasets are useful for training but can make evaluation look
        # falsely strong when their visual style leaks into every split.
        train_only = [path for path in unique_files if path.name.startswith(TRAIN_ONLY_PREFIXES)]
        independent = [path for path in unique_files if not path.name.startswith(TRAIN_ONLY_PREFIXES)]
        independent = sorted(independent, key=stable_key)[:MAX_INDEPENDENT_ORIGINALS_PER_CLASS]
        train_only = sorted(train_only, key=stable_key)[:MAX_TRAIN_ONLY_SOURCE_IMAGES_PER_CLASS]

        split_map = split_files(independent)
        split_map["train"].extend(train_only)
        for split, files in split_map.items():
            manifest[split][class_name] = []
            for index, source in enumerate(files):
                destination = output_root / split / class_name / f"{index:04d}_{source.stem}.jpg"
                image = source
                if source.suffix.lower() not in {".jpg", ".jpeg"}:
                    # Ultralytics/Pillow can read these, but standardize the
                    # extension and contents through the existing PIL runtime.
                    with Image.open(source) as opened:
                        opened.convert("RGB").save(destination, format="JPEG", quality=92)
                else:
                    shutil.copy2(image, destination)
                try:
                    manifest_path_value = str(destination.relative_to(ROOT))
                except ValueError:
                    manifest_path_value = str(destination)
                manifest[split][class_name].append(manifest_path_value)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for split in ("train", "val", "test"):
        counts = {class_name: len(manifest[split].get(class_name, [])) for class_name in CLASSES}
        print(split, counts)


if __name__ == "__main__":
    main()
