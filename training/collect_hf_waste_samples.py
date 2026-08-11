"""Collect review candidates from a permissively licensed image dataset.

Only source folders whose visual meaning is close to an app class are mapped.
The broad metal, paper and plastic folders are intentionally excluded because
they cannot distinguish the product-level classes used by SỌRT RÁC.
"""

from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "training" / "dataset" / "train"
SOURCES_PATH = ROOT / "training" / "hf-waste-sources.jsonl"
DATASET = "omasteam/waste-garbage-management-dataset"
API_ROOT = f"https://huggingface.co/api/datasets/{DATASET}/tree/main"
BASE_URL = f"https://huggingface.co/datasets/{DATASET}/resolve/main/"
USER_AGENT = "sort-rac-training-collector/2.1 (https://github.com/loulou675/S-RT-R-C)"

SOURCE_TO_APP = {
    "battery": "battery",
    "biological": "food_waste",
    "cardboard": "cardboard_box",
    "glass": "glass_drink_bottle",
}


def image_count(folder: Path, prefix: str) -> int:
    return len(list(folder.glob(f"{prefix}_*.jpg")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=60)
    args = parser.parse_args()

    with SOURCES_PATH.open("a", encoding="utf-8") as manifest:
        for source_class, app_class in SOURCE_TO_APP.items():
            destination = DATASET_ROOT / app_class
            destination.mkdir(parents=True, exist_ok=True)
            prefix = f"hf_{source_class}"
            existing = image_count(destination, prefix)
            needed = max(0, args.target - existing)
            if not needed:
                print(f"{app_class}: already has {args.target} {source_class} samples")
                continue

            response = requests.get(
                f"{API_ROOT}/{source_class}",
                params={"limit": min(1000, args.target * 3)},
                headers={"User-Agent": USER_AGENT},
                timeout=45,
            )
            response.raise_for_status()
            rows = response.json()
            added = 0
            for row in rows:
                if added >= needed:
                    break
                source_path = row.get("path")
                if not isinstance(source_path, str) or not source_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue
                try:
                    media = requests.get(BASE_URL + source_path, headers={"User-Agent": USER_AGENT}, timeout=(10, 45))
                    media.raise_for_status()
                    with Image.open(BytesIO(media.content)) as opened:
                        image = ImageOps.exif_transpose(opened).convert("RGB")
                    if min(image.size) < 96:
                        continue
                except Exception:  # noqa: BLE001 - one remote file must not stop the batch
                    continue
                output = destination / f"{prefix}_{existing + added:04d}.jpg"
                image.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                image.save(output, format="JPEG", quality=90, optimize=True)
                manifest.write(
                    json.dumps(
                        {
                            "class": app_class,
                            "source_class": source_class,
                            "local_file": str(output.relative_to(ROOT)),
                            "source_file": source_path,
                            "dataset": DATASET,
                            "dataset_url": f"https://huggingface.co/datasets/{DATASET}/tree/main/{source_class}",
                            "license": "MIT",
                            "review_status": "candidate",
                        }
                    )
                    + "\n"
                )
                manifest.flush()
                added += 1
            print(f"{app_class}: added {added} candidates from {source_class}", flush=True)


if __name__ == "__main__":
    main()
