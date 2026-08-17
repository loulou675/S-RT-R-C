"""Repeat rare training images without touching validation or test data."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
PREFIX = "oversample_"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--train",
        type=Path,
        default=ROOT / "training" / "classifier_dataset" / "train",
    )
    parser.add_argument("--minimum", type=int, default=90)
    args = parser.parse_args()

    for class_dir in sorted(path for path in args.train.iterdir() if path.is_dir()):
        for old_copy in class_dir.glob(f"{PREFIX}*"):
            old_copy.unlink()
        originals = sorted(
            path
            for path in class_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if not originals or len(originals) >= args.minimum:
            continue

        copies_needed = args.minimum - len(originals)
        for index in range(copies_needed):
            source = originals[index % len(originals)]
            destination = class_dir / f"{PREFIX}{index:04d}_{source.name}"
            os.link(source, destination)
        print(f"{class_dir.name}: {len(originals)} -> {args.minimum}")


if __name__ == "__main__":
    main()
