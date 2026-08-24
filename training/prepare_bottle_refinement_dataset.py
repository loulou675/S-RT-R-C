#!/usr/bin/env python3
"""Build an isolated v69 dataset with reviewed bottle-refinement images."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base = args.base.resolve()
    output = args.output.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    source = Path(manifest["source"]).resolve()
    target_class = manifest["targetClass"]
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {output}")
    for split in ("train", "val", "test"):
        if not (base / split).is_dir():
            raise SystemExit(f"Missing base split: {base / split}")

    # The active dataset lives in a separate worktree/volume where hard links
    # are not always permitted. Read-only symlinks keep the candidate isolated
    # without duplicating several gigabytes of source images.
    shutil.copytree(base, output, copy_function=os.symlink)
    destination = output / "train" / target_class
    existing_hashes = {
        digest(path)
        for path in destination.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    }
    added = []
    hard_negatives_added = []
    exact_duplicates = []
    for name in manifest["accepted"]:
        path = source / name
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            raise SystemExit(f"Accepted image is missing or unsupported: {path}")
        image_hash = digest(path)
        if image_hash in existing_hashes:
            exact_duplicates.append(name)
            continue
        target = destination / f"feedback-bottle-20260824-{name}"
        shutil.copy2(path, target)
        existing_hashes.add(image_hash)
        added.append(target.name)

    for class_name, names in manifest.get("hardNegativeLabels", {}).items():
        negative_destination = output / "train" / class_name
        if not negative_destination.is_dir():
            raise SystemExit(f"Hard-negative class is absent from base dataset: {class_name}")
        for name in names:
            path = source / name
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                raise SystemExit(f"Hard-negative image is missing or unsupported: {path}")
            image_hash = digest(path)
            if image_hash in existing_hashes:
                exact_duplicates.append(name)
                continue
            target = negative_destination / f"feedback-bottle-negative-20260824-{name}"
            shutil.copy2(path, target)
            existing_hashes.add(image_hash)
            hard_negatives_added.append({"file": target.name, "class": class_name})

    report = {
        "base": str(base),
        "manifest": str(args.manifest.resolve()),
        "output": str(output),
        "reviewedAccepted": len(manifest["accepted"]),
        "added": added,
        "hardNegativesAdded": hard_negatives_added,
        "exactDuplicatesSkipped": exact_duplicates,
        "rejected": manifest["rejected"],
    }
    (output / "bottle-refinement-build.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
