"""Collect targeted image subclasses from the public TrashBox repository.

This is for the local prototype only. The upstream repository does not include
an explicit LICENSE file, so the source log records that these images must not
be redistributed until their reuse terms are confirmed.
"""

from __future__ import annotations

import json
import re
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "training" / "dataset" / "train"
SOURCES_PATH = ROOT / "training" / "trashbox-sources.jsonl"
API_ROOT = "https://api.github.com/repos/nikhilvenkatkumsetty/TrashBox/contents/"
USER_AGENT = "sort-rac-local-dataset-collector/1.0"

TARGETS = {
    "aluminium_drink_can": "TrashBox_train_dataset_subfolders/metal/beverage cans",
    "cardboard_box": "TrashBox_train_dataset_subfolders/cardboard",
    "paper_cup": "TrashBox_train_dataset_subfolders/paper/paper cups",
    "plastic_takeaway_cup": "TrashBox_train_dataset_subfolders/plastic/plastic cups",
    "plastic_water_bottle": "TrashBox_train_dataset_subfolders/plastic/plastic bottles",
    "unknown": "TrashBox_train_dataset_subfolders/glass",
}


def list_images(repo_path: str) -> list[dict]:
    response = requests.get(
        API_ROOT + quote(repo_path),
        params={"ref": "main", "per_page": 100},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return [entry for entry in response.json() if entry.get("type") == "file" and entry.get("download_url")]


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value)


def collect_class(class_name: str, repo_path: str, target: int, source_file) -> int:
    destination = DATASET_ROOT / class_name
    destination.mkdir(parents=True, exist_ok=True)
    existing = len(list(destination.glob("trashbox_*.jpg")))
    if existing >= target:
        return 0

    added = 0
    for entry in list_images(repo_path):
        if existing + added >= target:
            break
        try:
            response = requests.get(entry["download_url"], headers={"User-Agent": USER_AGENT}, timeout=30)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content)).convert("RGB")
            if min(image.size) < 128:
                continue
            filename = destination / f"trashbox_{safe_name(entry['name'])}"
            filename = filename.with_suffix(".jpg")
            if filename.exists():
                continue
            image.save(filename, format="JPEG", quality=92, optimize=True)
        except Exception as error:  # noqa: BLE001 - skip an unreadable source file
            print(f"skip {entry.get('name')}: {error}")
            continue

        record = {
            "class": class_name,
            "local_file": str(filename.relative_to(ROOT)),
            "source_url": entry["html_url"],
            "download_url": entry["download_url"],
            "source_repository": "https://github.com/nikhilvenkatkumsetty/TrashBox",
            "license_note": "The upstream repository does not include an explicit LICENSE file; local prototype use only until reuse terms are confirmed.",
        }
        source_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        source_file.flush()
        added += 1
        print(f"{class_name}: added {filename.name}")
        time.sleep(0.1)

    return added


def main() -> None:
    with SOURCES_PATH.open("a", encoding="utf-8") as source_file:
        for class_name, repo_path in TARGETS.items():
            added = collect_class(class_name, repo_path, target=15, source_file=source_file)
            print(f"{class_name}: added {added} new training images")


if __name__ == "__main__":
    main()
