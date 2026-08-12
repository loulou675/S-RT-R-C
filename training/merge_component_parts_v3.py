#!/usr/bin/env python3
"""Merge the reviewed closure baseline with independent Open Images straws."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOSURE = ROOT / "training" / "component_dataset_closure_eval"
STRAW = ROOT / "training" / "openimages_component_straw"
PACKWISE_CLOSURE = ROOT / "training" / "packwise_component_closure"
DEFAULT_OUTPUT = ROOT / "training" / "component_dataset_parts_v3"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {output}")

    for split in ("train", "val", "test"):
        for task in ("images", "labels"):
            (output / task / split).mkdir(parents=True, exist_ok=True)

        for image in (CLOSURE / "images" / split).glob("*.jpg"):
            shutil.copy2(image, output / "images" / split / f"closure_{image.name}")
            label = CLOSURE / "labels" / split / f"{image.stem}.txt"
            shutil.copy2(label, output / "labels" / split / f"closure_{label.name}")

        for image in (STRAW / "images" / split).glob("*.jpg"):
            shutil.copy2(image, output / "images" / split / f"straw_{image.name}")
            label = STRAW / "labels" / split / f"{image.stem}.txt"
            rows = []
            for line in label.read_text(encoding="utf-8").splitlines():
                values = line.split()
                if len(values) == 5:
                    rows.append("1 " + " ".join(values[1:]))
            (output / "labels" / split / f"straw_{label.name}").write_text("\n".join(rows) + "\n", encoding="utf-8")

        if PACKWISE_CLOSURE.exists():
            for image in (PACKWISE_CLOSURE / "images" / split).glob("*.jpg"):
                shutil.copy2(image, output / "images" / split / f"packwise_{image.name}")
                label = PACKWISE_CLOSURE / "labels" / split / f"{image.stem}.txt"
                shutil.copy2(label, output / "labels" / split / f"packwise_{label.name}")

    yaml = [f"path: {output}", "train: images/train", "val: images/val", "test: images/test", "names:", "  0: closure", "  1: straw"]
    (output / "data.yaml").write_text("\n".join(yaml) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
