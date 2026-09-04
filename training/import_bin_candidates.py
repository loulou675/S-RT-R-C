"""Add broad new-item images directly to the disposal-bin classifier dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_TO_BIN = {
    "broken_ceramic": "landfill",
    "clothing_fabric": "landfill",
    "comb": "landfill",
    "cosmetic_sponge": "landfill",
    "eraser": "landfill",
    "glue_tape": "landfill",
    "keychain": "landfill",
    "notebook": "paper_cardboard",
    "pencil_crayon": "landfill",
    "phone_charger": "hazardous",
    "ruler": "landfill",
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
PREFIX = "broad_candidate__"


def split_images(class_code: str, paths: list[Path]) -> dict[str, list[Path]]:
    ordered = sorted(
        paths,
        key=lambda path: hashlib.sha256(f"{class_code}:{path.name}".encode()).hexdigest(),
    )
    count = len(ordered)
    if count < 3:
        return {"train": ordered, "val": [], "test": []}
    if count < 10:
        return {"train": ordered[:-2], "val": ordered[-2:-1], "test": ordered[-1:]}

    val_count = max(1, round(count * 0.15))
    test_count = max(1, round(count * 0.15))
    train_end = count - val_count - test_count
    return {
        "train": ordered[:train_end],
        "val": ordered[train_end : train_end + val_count],
        "test": ordered[train_end + val_count :],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "training" / "candidate_dataset" / "new_items",
    )
    parser.add_argument("--dataset", type=Path, default=ROOT / "training" / "bin_dataset")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "training" / "source_manifests" / "bin-candidate-import.jsonl",
    )
    args = parser.parse_args()

    for split in ("train", "val", "test"):
        for bin_code in set(SOURCE_TO_BIN.values()):
            destination = args.dataset / split / bin_code
            destination.mkdir(parents=True, exist_ok=True)
            for old_path in destination.glob(f"{PREFIX}*"):
                old_path.unlink()

    rows: list[dict[str, str]] = []
    counts: dict[tuple[str, str], int] = {}
    for source_code, bin_code in SOURCE_TO_BIN.items():
        source_dir = args.source / source_code
        images = [
            path
            for path in source_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ] if source_dir.exists() else []

        for split, split_images_list in split_images(source_code, images).items():
            destination = args.dataset / split / bin_code
            for index, image_path in enumerate(split_images_list):
                digest = hashlib.sha256(image_path.read_bytes()).hexdigest()[:12]
                target = destination / f"{PREFIX}{source_code}__{index:03d}__{digest}{image_path.suffix.lower()}"
                os.link(image_path, target)
                counts[(split, source_code)] = counts.get((split, source_code), 0) + 1
                rows.append(
                    {
                        "source_code": source_code,
                        "bin_code": bin_code,
                        "split": split,
                        "source": str(image_path.relative_to(ROOT)),
                        "target": str(target.relative_to(ROOT)),
                        "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                    }
                )

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    for source_code in SOURCE_TO_BIN:
        summary = ", ".join(
            f"{split}={counts.get((split, source_code), 0)}"
            for split in ("train", "val", "test")
        )
        print(f"{source_code}: {summary}")
    print(f"Imported {len(rows)} broad candidate images")


if __name__ == "__main__":
    main()

