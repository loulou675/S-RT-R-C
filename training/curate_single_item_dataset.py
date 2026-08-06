"""Quarantine images that do not match the one-item training contract.

The operation is reversible: files are moved under ``training/quarantine`` and
their original paths are recorded in a manifest. Nothing is deleted.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRAIN_ROOT = ROOT / "training" / "dataset" / "train"
QUARANTINE_ROOT = ROOT / "training" / "quarantine"
MANIFEST_PATH = QUARANTINE_ROOT / "manifest.jsonl"

# These downloaded images are visibly cluttered, contain multiple objects, or
# carry stock-photo watermarks. They should not teach the classifier a class.
EXPLICIT_BAD = {
    "aluminium_drink_can": {
        "crumpled-empty-blank-aluminium-can-600w-2703908305.webp",
        "images.jpeg",
    },
    "battery": {
        "XMS24BATAA8_1024x1024.webp",
        "commons_15359691.jpg",
        "commons_15852351.jpg",
        "commons_282602.jpg",
        "commons_52898.jpg",
    },
    "cardboard_box": {
        "commons_72384486.jpg",
        "commons_87745811.jpg",
        "images.jpeg",
    },
    "fruit_peel": {"images (2).jpeg"},
    "paper_cup": {"logo-printed-paper-cup.jpg"},
    "plastic_takeaway_cup": {
        "set-realistic-plastic-disposable-food-glasses-various-size-white-isolated_1284-28031.avif",
    },
    "plastic_water_bottle": {"images.jpeg"},
}

MISCLASSIFIED_TO_UNKNOWN = {
    "aluminium_drink_can": {
        "trashnet_metal_006.jpg",
        "trashnet_metal_012.jpg",
        "trashnet_metal_017.jpg",
        "trashnet_metal_018.jpg",
        "trashnet_metal_020.jpg",
        "trashnet_metal_021.jpg",
        "trashnet_metal_024.jpg",
        "trashnet_metal_026.jpg",
        "trashnet_metal_029.jpg",
    },
    "battery": {
        "commons_real_129248138.jpg",
        "commons_real_94332223.jpg",
        "commons_real_97449028.jpg",
    },
    "cardboard_box": {
        "commons_real_94851437.jpg",
        "commons_real_110049916.jpg",
    },
    "plastic_takeaway_cup": {"commons_real_35562638.jpg"},
}


def quarantine(path: Path, reason: str) -> None:
    relative = path.relative_to(TRAIN_ROOT)
    destination = QUARANTINE_ROOT / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    shutil.move(str(path), str(destination))
    with MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
        manifest.write(
            json.dumps(
                {
                    "original": str((TRAIN_ROOT / relative).relative_to(ROOT)),
                    "quarantined": str(destination.relative_to(ROOT)),
                    "reason": reason,
                }
            )
            + "\n"
        )
    print(f"quarantined {relative} ({reason})")


def main() -> None:
    QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)

    for class_name, filenames in EXPLICIT_BAD.items():
        for filename in filenames:
            path = TRAIN_ROOT / class_name / filename
            if path.exists():
                quarantine(path, "multiple items, cluttered scene, or visible stock watermark")

    # Preserve single-item negatives, but do not leave them in a target class.
    unknown_destination = TRAIN_ROOT / "unknown"
    unknown_destination.mkdir(parents=True, exist_ok=True)
    for class_name, filenames in MISCLASSIFIED_TO_UNKNOWN.items():
        for filename in filenames:
            path = TRAIN_ROOT / class_name / filename
            if not path.exists():
                continue
            destination = unknown_destination / f"from_{class_name}_{filename}"
            shutil.move(str(path), str(destination))
            with MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
                manifest.write(
                    json.dumps(
                        {
                            "original": str(path.relative_to(ROOT)),
                            "moved_to": str(destination.relative_to(ROOT)),
                            "reason": "single object, but not the target class",
                        }
                    )
                    + "\n"
                )
            print(f"moved {path.relative_to(ROOT)} to unknown/")

    # The file is a single car battery, so it is more useful as a battery
    # example than as an unknown example. Move it without discarding it.
    misplaced = TRAIN_ROOT / "unknown" / "images (1).jpeg"
    if misplaced.exists():
        destination = TRAIN_ROOT / "battery" / misplaced.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(misplaced), str(destination))
        with MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
            manifest.write(
                json.dumps(
                    {
                        "original": "training/dataset/train/unknown/images (1).jpeg",
                        "moved_to": "training/dataset/train/battery/images (1).jpeg",
                        "reason": "single battery item was in the unknown folder",
                    }
                )
                + "\n"
            )
        print("moved unknown/images (1).jpeg to battery/")

    # TrashBox samples are held separately until their reuse terms and visual
    # composition are confirmed; the reviewed samples contain clutter or piles.
    for path in sorted(TRAIN_ROOT.glob("*/trashbox_*.jpg")):
        quarantine(path, "unverified source and reviewed samples contain multiple items or clutter")


if __name__ == "__main__":
    main()
