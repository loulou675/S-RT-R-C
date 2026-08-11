"""Extract a reviewed-size aluminium-can candidate batch from a CC0 dataset.

The upstream archive contains many consecutive frames of the same physical
cans. This script intentionally samples a small set of frames and writes them
to ``training/source_review`` instead of placing them directly in a split.
Review the contact sheet before admitting candidates to training, and keep all
images from this source out of validation/test to avoid sequence leakage.
"""

from __future__ import annotations

import argparse
import json
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/arkadiyhacks/drinking-waste-classification"
SOURCE_PAGE = "https://www.kaggle.com/datasets/arkadiyhacks/drinking-waste-classification"
DEFAULT_ARCHIVE = Path("/tmp/sort-rac-drinking-waste.zip")
OUTPUT_ROOT = ROOT / "training" / "source_review" / "drinking_waste_aluminium_crops"
MANIFEST_PATH = ROOT / "training" / "drinking-waste-cc0-sources.jsonl"

# Sparse samples across the video-like sequences. Consecutive frames are
# deliberately omitted because they add volume without much new information.
SELECTED_FRAME_IDS = (
    2, 14, 25, 36, 47, 58, 69, 80, 91, 103,
    114, 158, 202, 246, 290, 323, 367,
    389, 433, 477, 521, 565, 609, 653, 697,
    708, 752, 796, 840, 884, 928,
    939, 950, 961, 972, 983, 994, 1005, 1016, 1027, 1038, 1049, 1060,
)


def frame_id(path: str) -> int:
    stem = Path(path).stem.replace("AluCan", "")
    return int(re.sub(r"\D", "", stem))


def download_archive(path: Path) -> None:
    if path.exists() and path.stat().st_size > 100_000_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(DOWNLOAD_URL, stream=True, timeout=(20, 180)) as response:
        response.raise_for_status()
        with path.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                output.write(chunk)


def crop_from_yolo(image: Image.Image, label: str) -> Image.Image | None:
    boxes = []
    for line in label.splitlines():
        values = line.split()
        if len(values) != 5:
            continue
        _, cx, cy, width, height = map(float, values)
        boxes.append((cx, cy, width, height))
    if not boxes:
        return None

    cx, cy, width, height = max(boxes, key=lambda box: box[2] * box[3])
    x1 = (cx - width / 2) * image.width
    y1 = (cy - height / 2) * image.height
    x2 = (cx + width / 2) * image.width
    y2 = (cy + height / 2) * image.height
    padding = 0.30 * max(x2 - x1, y2 - y1)
    left = max(0, round(x1 - padding))
    top = max(0, round(y1 - padding))
    right = min(image.width, round(x2 + padding))
    bottom = min(image.height, round(y2 + padding))
    if right - left < 96 or bottom - top < 96:
        return None
    return image.crop((left, top, right, bottom))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    download_archive(args.archive)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    existing = {
        json.loads(line).get("frame_id")
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    } if MANIFEST_PATH.exists() else set()

    with ZipFile(args.archive) as archive, MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
        image_paths = {
            frame_id(name): name
            for name in archive.namelist()
            if name.startswith("Images_of_Waste/YOLO_imgs/AluCan")
            and name.lower().endswith((".jpg", ".jpeg", ".png"))
        }
        added = 0
        for value in SELECTED_FRAME_IDS:
            if value in existing or value not in image_paths:
                continue
            image_path = image_paths[value]
            label_path = str(Path(image_path).with_suffix(".txt"))
            try:
                with Image.open(BytesIO(archive.read(image_path))) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                crop = crop_from_yolo(image, archive.read(label_path).decode("utf-8"))
            except KeyError:
                continue
            if crop is None:
                continue
            crop.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            output = OUTPUT_ROOT / f"drinking_waste_cc0_{value:04d}.jpg"
            crop.save(output, "JPEG", quality=91, optimize=True)
            manifest.write(json.dumps({
                "class": "aluminium_drink_can",
                "frame_id": value,
                "source_file": image_path,
                "local_file": str(output.relative_to(ROOT)),
                "dataset": "Drinking Waste Classification",
                "source_page": SOURCE_PAGE,
                "license": "CC0: Public Domain",
                "review_status": "candidate",
                "split_hint": "train_only_sequence",
            }) + "\n")
            manifest.flush()
            existing.add(value)
            added += 1
        print(f"Added {added} CC0 aluminium-can review crops to {OUTPUT_ROOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
