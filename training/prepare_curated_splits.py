"""Build reproducible train/validation/test folders from reviewed images."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "training" / "dataset"
OUTPUT_ROOT = ROOT / "training" / "dataset_curated"
MANIFEST_PATH = ROOT / "training" / "curated-split.json"
CLASSES = json.loads((ROOT / "training" / "classes.json").read_text(encoding="utf-8"))["classes"]

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
    if OUTPUT_ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing curated dataset: {OUTPUT_ROOT}")

    for split in ("train", "val", "test"):
        for class_name in CLASSES:
            (OUTPUT_ROOT / split / class_name).mkdir(parents=True, exist_ok=True)

    seen_hashes: set[str] = set()
    manifest: dict[str, dict[str, list[str]]] = {split: {} for split in ("train", "val", "test")}

    for class_name in CLASSES:
        candidates = []
        for source_split in ("train", "val", "test"):
            candidates.extend(
                path
                for path in (SOURCE_ROOT / source_split / class_name).iterdir()
                if path.is_file() and path.name not in {".gitkeep", ".DS_Store"} and str(path.relative_to(ROOT)) not in EXCLUDE
            )

        unique_files = []
        for path in sorted(candidates):
            file_hash = digest(path)
            if file_hash in seen_hashes:
                continue
            seen_hashes.add(file_hash)
            unique_files.append(path)

        for split, files in split_files(unique_files).items():
            manifest[split][class_name] = []
            for index, source in enumerate(files):
                destination = OUTPUT_ROOT / split / class_name / f"{index:04d}_{source.stem}.jpg"
                image = source
                if source.suffix.lower() not in {".jpg", ".jpeg"}:
                    # Ultralytics/Pillow can read these, but standardize the
                    # extension and contents through the existing PIL runtime.
                    from PIL import Image

                    with Image.open(source) as opened:
                        opened.convert("RGB").save(destination, format="JPEG", quality=92)
                else:
                    shutil.copy2(image, destination)
                manifest[split][class_name].append(str(destination.relative_to(ROOT)))

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for split in ("train", "val", "test"):
        counts = {class_name: len(manifest[split].get(class_name, [])) for class_name in CLASSES}
        print(split, counts)


if __name__ == "__main__":
    main()
