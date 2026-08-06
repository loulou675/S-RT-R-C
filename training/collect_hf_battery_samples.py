"""Add a small battery review batch from the MIT-licensed HF waste dataset."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "training" / "dataset" / "train" / "battery"
SOURCES_PATH = ROOT / "training" / "hf-battery-sources.jsonl"
API_URL = "https://huggingface.co/api/datasets/omasteam/waste-garbage-management-dataset/tree/main/battery"
BASE_URL = "https://huggingface.co/datasets/omasteam/waste-garbage-management-dataset/resolve/main/"
USER_AGENT = "sort-rac-local-hf-battery-collector/1.0 (single-item research prototype)"


def main() -> None:
    response = requests.get(API_URL, params={"limit": 80}, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    rows = response.json()
    DESTINATION.mkdir(parents=True, exist_ok=True)
    existing = len(list(DESTINATION.glob("hf_battery_field_*.jpg")))
    needed = max(0, 20 - existing)
    with SOURCES_PATH.open("a", encoding="utf-8") as log:
        added = 0
        for row in rows:
            if added >= needed:
                break
            path = row.get("path")
            if not isinstance(path, str) or not path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            try:
                media = requests.get(BASE_URL + path, headers={"User-Agent": USER_AGENT}, timeout=(10, 30))
                media.raise_for_status()
                image = Image.open(BytesIO(media.content)).convert("RGB")
                if min(image.size) < 96:
                    continue
            except Exception:  # noqa: BLE001 - skip a broken remote file
                continue
            output = DESTINATION / f"hf_battery_field_{added:03d}.jpg"
            image.save(output, format="JPEG", quality=92, optimize=True)
            log.write(json.dumps({
                "class": "battery",
                "local_file": str(output.relative_to(ROOT)),
                "source_file": path,
                "dataset": "omasteam/waste-garbage-management-dataset",
                "dataset_url": "https://huggingface.co/datasets/omasteam/waste-garbage-management-dataset/tree/main/battery",
                "license": "MIT",
            }) + "\n")
            log.flush()
            added += 1
            print(f"added {output.name}", flush=True)
    print(f"battery: added {added} review candidates", flush=True)


if __name__ == "__main__":
    main()
