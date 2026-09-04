"""Balance one component class by duplicating only its training images.

Validation and test data are intentionally left untouched so evaluation remains
representative. Re-running the script is safe because generated filenames are
ignored when selecting source images.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("training/component_dataset"))
    parser.add_argument("--class-id", type=int, required=True)
    parser.add_argument("--copies", type=int, default=3)
    return parser.parse_args()


def contains_class(label_path: Path, class_id: int) -> bool:
    return any(
        line.split(maxsplit=1)[0] == str(class_id)
        for line in label_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def find_image(images_dir: Path, stem: str) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        candidate = images_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def main() -> None:
    args = parse_args()
    images_dir = args.dataset / "images" / "train"
    labels_dir = args.dataset / "labels" / "train"
    marker = f"__oversample_c{args.class_id}_"
    created = 0

    source_labels = [
        path
        for path in sorted(labels_dir.glob("*.txt"))
        if marker not in path.stem and contains_class(path, args.class_id)
    ]
    for label_path in source_labels:
        image_path = find_image(images_dir, label_path.stem)
        if image_path is None:
            raise FileNotFoundError(f"Missing image for {label_path}")

        for copy_index in range(1, args.copies + 1):
            target_stem = f"{label_path.stem}{marker}{copy_index}"
            target_label = labels_dir / f"{target_stem}.txt"
            target_image = images_dir / f"{target_stem}{image_path.suffix.lower()}"
            if target_label.exists() and target_image.exists():
                continue
            shutil.copy2(label_path, target_label)
            shutil.copy2(image_path, target_image)
            created += 1

    print(f"Sources containing class {args.class_id}: {len(source_labels)}")
    print(f"Created training duplicates: {created}")


if __name__ == "__main__":
    main()
