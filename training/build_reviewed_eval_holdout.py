#!/usr/bin/env python3
"""Replace generated eval splits with reviewed, non-overlapping holdouts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def source_stem(path: Path) -> str:
    return re.sub(r"^\d{4}_", "", path.stem)


def source_group(stem: str) -> str:
    taco = re.match(r"taco_field_v2_(\d+)_", stem)
    if taco:
        return f"taco-image-{taco.group(1)}"
    return stem


def stable(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda path: hashlib.sha256(str(path).encode()).hexdigest())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=ROOT / "training" / "dataset_curated")
    parser.add_argument("--minimum", type=int, default=3)
    parser.add_argument("--maximum", type=int, default=8)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    data = args.data.resolve()
    reference = args.reference.resolve()
    rejected = {
        path.stem
        for path in (ROOT / "training" / "review_rejected").glob("*/*")
        if path.is_file()
    }
    report: dict[str, dict[str, list[str]]] = {"val": {}, "test": {}}

    classes = sorted(path.name for path in (data / "train").iterdir() if path.is_dir())
    for class_name in classes:
        train_dir = data / "train" / class_name
        train_files = [path for path in train_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS]
        by_stem = {source_stem(path): path for path in train_files}
        used_stems: set[str] = set()
        used_groups: set[str] = set()

        for split in ("val", "test"):
            destination_dir = data / split / class_name
            destination_dir.mkdir(parents=True, exist_ok=True)
            for old in destination_dir.iterdir():
                if old.is_file() and old.name != ".gitkeep":
                    old.unlink()

            reference_candidates = []
            reference_dir = reference / split / class_name
            if reference_dir.exists():
                reference_candidates = [
                    path
                    for path in reference_dir.iterdir()
                    if path.suffix.lower() in IMAGE_EXTENSIONS
                    and source_stem(path) not in rejected
                    and source_group(source_stem(path)) not in used_groups
                ]

            selected = stable(reference_candidates)[: args.maximum]
            for source in selected:
                stem = source_stem(source)
                used_stems.add(stem)
                used_groups.add(source_group(stem))

            if len(selected) < args.minimum:
                fallback = [
                    path
                    for stem, path in by_stem.items()
                    if stem not in used_stems and source_group(stem) not in used_groups
                ]
                needed = args.minimum - len(selected)
                for source in stable(fallback)[:needed]:
                    stem = source_stem(source)
                    selected.append(source)
                    used_stems.add(stem)
                    used_groups.add(source_group(stem))

            report[split][class_name] = []
            for index, source in enumerate(selected):
                stem = source_stem(source)
                train_copy = by_stem.get(stem)
                destination = destination_dir / f"{index:04d}_{stem}.jpg"
                if train_copy and train_copy.exists() and source.resolve() == train_copy.resolve():
                    shutil.move(str(source), destination)
                else:
                    if train_copy and train_copy.exists():
                        train_copy.unlink()
                    shutil.copy2(source, destination)
                report[split][class_name].append(str(destination.relative_to(ROOT)))

    args.manifest.resolve().write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for split in ("val", "test"):
        counts = {name: len(files) for name, files in report[split].items()}
        print(split, counts)


if __name__ == "__main__":
    main()
