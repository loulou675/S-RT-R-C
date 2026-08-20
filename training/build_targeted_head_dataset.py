#!/usr/bin/env python3
"""Build a small train split with full immutable validation/test splits."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from PIL import Image, ImageOps


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def images(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-classes", nargs="+", required=True)
    parser.add_argument("--cap", action="append", default=[])
    parser.add_argument(
        "--train-max-dimension",
        type=int,
        default=0,
        help="Optionally normalize train images to this maximum side length.",
    )
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {output}")
    caps = {}
    for value in args.cap:
        class_name, count = value.split("=", 1)
        caps[class_name] = int(count)

    split_hashes: dict[str, set[str]] = {"train": set(), "val": set(), "test": set()}
    for split in ("val", "test"):
        for class_dir in sorted(path for path in (source / split).iterdir() if path.is_dir()):
            destination = output / split / class_dir.name
            destination.mkdir(parents=True, exist_ok=True)
            for path in images(class_dir):
                os.link(path, destination / path.name)
                split_hashes[split].add(hashlib.sha256(path.read_bytes()).hexdigest())

    for class_name in args.train_classes:
        class_dir = source / "train" / class_name
        if not class_dir.is_dir():
            raise SystemExit(f"Missing train class: {class_name}")
        paths = images(class_dir)
        if class_name in caps:
            paths = paths[: caps[class_name]]
        destination = output / "train" / class_name
        destination.mkdir(parents=True, exist_ok=True)
        for path in paths:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in split_hashes["val"] or digest in split_hashes["test"]:
                raise SystemExit(f"Train/held-out overlap: {path}")
            if args.train_max_dimension:
                with Image.open(path) as raw:
                    image = ImageOps.exif_transpose(raw).convert("RGB")
                image.thumbnail(
                    (args.train_max_dimension, args.train_max_dimension),
                    Image.Resampling.LANCZOS,
                )
                image.save(destination / f"{path.stem}.jpg", "JPEG", quality=90, optimize=True)
            else:
                os.link(path, destination / path.name)
            split_hashes["train"].add(digest)
        print(f"{class_name:<24} train={len(paths):>4}")
    print(f"Created targeted head dataset at {output}")


if __name__ == "__main__":
    main()
