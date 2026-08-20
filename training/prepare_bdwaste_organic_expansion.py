#!/usr/bin/env python3
"""Prepare a visually diverse, traceable BDWaste organic training subset.

The source archives contain many adjacent/near-duplicate captures. This script
uses a deterministic perceptual-hash farthest-first selection so a requested
quota represents visual variety rather than repeated frames. Output images are
resized and re-encoded for efficient local training; validation and test data
are never touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SOURCE_URL = "https://data.mendeley.com/datasets/96g5pgfnfw/1"
SOURCE_DOI = "10.17632/96g5pgfnfw.1"
SOURCE_LICENSE = "CC BY 4.0"
SOURCE_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

SOURCE_RULES = {
    "9. Banana peel": ("fruit_peel", 52),
    "8.Lemon Peel": ("fruit_peel", 24),
    "5. Mango Peel": ("fruit_peel", 2),
    "7. Shell of Malta": ("fruit_peel", 2),
    "3. Potato Peel": ("vegetable_scraps", 80),
}


def natural_key(path: Path) -> tuple:
    return tuple(
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.name)
    )


def eligible(path: Path, source_name: str) -> bool:
    """Exclude visibly ambiguous source frames identified during contact-sheet review."""
    numbers = [int(value) for value in re.findall(r"\d+", path.stem)]
    number = numbers[0] if numbers else -1
    if source_name == "5. Mango Peel" and number > 60:
        # Later frames prominently include whole mangoes, not discarded peel.
        return False
    if source_name == "9. Banana peel" and number == 116:
        # This frame is a whole bunch of bananas.
        return False
    return True


def perceptual_hash(path: Path) -> np.ndarray:
    size = 32
    retained = 8
    with Image.open(path) as image:
        pixels = np.asarray(
            ImageOps.exif_transpose(image).convert("L").resize(
                (size, size), Image.Resampling.LANCZOS
            ),
            dtype=np.float32,
        )
    positions = np.arange(size)
    frequencies = np.arange(size)[:, None]
    cosine = np.cos(np.pi * (2 * positions + 1) * frequencies / (2 * size))
    cosine[0] *= 1 / math.sqrt(2)
    cosine *= math.sqrt(2 / size)
    coefficients = cosine @ pixels @ cosine.T
    low_frequency = coefficients[:retained, :retained].reshape(-1)[1:]
    return low_frequency > np.median(low_frequency)


def hamming(left: np.ndarray, right: np.ndarray) -> int:
    return int(np.count_nonzero(left != right))


def diverse_selection(paths: list[Path], quota: int) -> list[Path]:
    """Select deterministic farthest-first representatives in perceptual-hash space."""
    paths = sorted(paths, key=natural_key)
    hashes = [perceptual_hash(path) for path in paths]
    if len(paths) <= quota:
        return paths

    # Begin at the item farthest from the set medoid, then repeatedly maximize
    # distance to the nearest already selected item.
    total_distances = [sum(hamming(value, other) for other in hashes) for value in hashes]
    selected = [max(range(len(paths)), key=lambda index: (total_distances[index], -index))]
    nearest = [hamming(value, hashes[selected[0]]) for value in hashes]
    while len(selected) < quota:
        candidates = (index for index in range(len(paths)) if index not in selected)
        next_index = max(candidates, key=lambda index: (nearest[index], -index))
        selected.append(next_index)
        for index, value in enumerate(hashes):
            nearest[index] = min(nearest[index], hamming(value, hashes[next_index]))
    return [paths[index] for index in sorted(selected)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-dimension", type=int, default=1600)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {output}")

    manifest_entries = []
    totals: dict[str, int] = {}
    for source_name, (target_class, quota) in SOURCE_RULES.items():
        source_dir = next(
            (path for path in source.iterdir() if path.is_dir() and path.name.strip() == source_name),
            None,
        )
        if source_dir is None:
            raise SystemExit(f"Missing extracted source directory: {source_name}")
        candidates = [
            path
            for path in source_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in IMAGE_SUFFIXES
            and eligible(path, source_name)
        ]
        chosen = diverse_selection(candidates, quota)
        target_dir = output / target_class
        target_dir.mkdir(parents=True, exist_ok=True)
        source_slug = re.sub(r"[^a-z0-9]+", "_", source_name.lower()).strip("_")
        for sequence, path in enumerate(chosen, start=1):
            destination = target_dir / f"expansion_bdwaste_{source_slug}_{sequence:03d}.jpg"
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail(
                    (args.max_dimension, args.max_dimension), Image.Resampling.LANCZOS
                )
                image.save(destination, "JPEG", quality=92, optimize=True)
            manifest_entries.append(
                {
                    "source_category": source_name,
                    "source_filename": path.name,
                    "target_class": target_class,
                    "output_filename": destination.name,
                    "source_sha256": sha256(path),
                    "output_sha256": sha256(destination),
                }
            )
            totals[target_class] = totals.get(target_class, 0) + 1

    manifest = {
        "dataset": "BDWaste",
        "source_url": SOURCE_URL,
        "doi": SOURCE_DOI,
        "license": SOURCE_LICENSE,
        "license_url": SOURCE_LICENSE_URL,
        "changes": "Selected for visual diversity, resized to a maximum dimension of 1600px, and JPEG re-encoded.",
        "selection": "Deterministic perceptual-hash farthest-first sampling after contact-sheet ambiguity review.",
        "totals": totals,
        "images": manifest_entries,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    for class_name, count in sorted(totals.items()):
        print(f"{class_name}: {count}")
    print(f"Prepared expansion at {output}")


if __name__ == "__main__":
    main()
