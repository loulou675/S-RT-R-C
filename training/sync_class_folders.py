"""Create the train/val/test folder contract from training/classes.json."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "training" / "dataset"
CLASSES = json.loads((ROOT / "training" / "classes.json").read_text(encoding="utf-8"))["classes"]


def main() -> None:
    for split in ("train", "val", "test"):
        for class_name in CLASSES:
            folder = DATASET / split / class_name
            folder.mkdir(parents=True, exist_ok=True)
            placeholder = folder / ".gitkeep"
            if not any(path.is_file() and path.name != ".gitkeep" for path in folder.iterdir()):
                placeholder.touch(exist_ok=True)
    print(f"Prepared {len(CLASSES)} class folders in train, val and test.")


if __name__ == "__main__":
    main()
