#!/usr/bin/env python3
"""Build an immutable training view without generated oversample copies.

The source classifier dataset remains untouched. Files are hard-linked into a
new candidate directory so the view is cheap to create while preserving the
exact train/validation/test split.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def image_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "training" / "classifier_dataset",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--exclude-class",
        action="append",
        default=[],
        help="Class folder to omit from every split. May be supplied more than once.",
    )
    parser.add_argument(
        "--extra-train-root",
        action="append",
        type=Path,
        default=[],
        help="Optional class-folder root whose images are added to train only.",
    )
    parser.add_argument(
        "--exclude-train-prefix",
        action="append",
        default=["oversample_"],
        help="Training filename prefix to omit. May be supplied more than once.",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing candidate dataset: {output}")

    counts: dict[str, dict[str, int]] = defaultdict(dict)
    split_hashes: dict[str, set[str]] = defaultdict(set)
    excluded_classes = set(args.exclude_class)
    for split in ("train", "val", "test"):
        split_root = source / split
        for class_dir in sorted(path for path in split_root.iterdir() if path.is_dir()):
            if class_dir.name in excluded_classes:
                continue
            destination = output / split / class_dir.name
            destination.mkdir(parents=True, exist_ok=True)
            paths = image_files(class_dir)
            if split == "train":
                paths = [
                    path
                    for path in paths
                    if not any(
                        path.name.startswith(prefix) for prefix in args.exclude_train_prefix
                    )
                ]
            for path in paths:
                os.link(path, destination / path.name)
                split_hashes[split].add(hashlib.sha256(path.read_bytes()).hexdigest())
            counts[class_dir.name][split] = len(paths)

    for extra_root in args.extra_train_root:
        extra_root = extra_root.resolve()
        for class_dir in sorted(path for path in extra_root.iterdir() if path.is_dir()):
            if class_dir.name in excluded_classes:
                continue
            if class_dir.name not in counts:
                raise SystemExit(f"Extra train root contains unknown class: {class_dir.name}")
            destination = output / "train" / class_dir.name
            paths = image_files(class_dir)
            for path in paths:
                target = destination / path.name
                if target.exists():
                    raise SystemExit(f"Extra training filename collision: {target}")
                image_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                if image_hash in split_hashes["val"] or image_hash in split_hashes["test"]:
                    raise SystemExit(f"Extra training image overlaps a held-out split: {path}")
                os.link(path, target)
                split_hashes["train"].add(image_hash)
            counts[class_dir.name]["train"] = counts[class_dir.name].get("train", 0) + len(paths)

    overlap = (
        (split_hashes["train"] & split_hashes["val"])
        | (split_hashes["train"] & split_hashes["test"])
        | (split_hashes["val"] & split_hashes["test"])
    )
    if overlap:
        raise SystemExit(f"Candidate view contains {len(overlap)} cross-split duplicate hashes")

    for class_name, class_counts in sorted(counts.items()):
        print(
            f"{class_name:<29} "
            f"train={class_counts.get('train', 0):>4} "
            f"val={class_counts.get('val', 0):>3} "
            f"test={class_counts.get('test', 0):>3}"
        )
    print(f"\nCreated controlled candidate dataset at {output}")


if __name__ == "__main__":
    main()
