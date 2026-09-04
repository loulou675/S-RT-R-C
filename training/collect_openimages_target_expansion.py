#!/usr/bin/env python3
"""Collect train-only Open Images candidates for selected weak classes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ROOT = ROOT / "training" / "candidate_dataset" / "target_expansion" / "openimages"
MANIFEST = ROOT / "training" / "source_manifests" / "openimages-target-expansion-candidates.jsonl"
CACHE = Path("/tmp/sort-rac-openimages-target-expansion")
CLASSES_URL = "https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions-boxable.csv"
BOXES_URL = "https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv"
IMAGE_URL = "https://open-images-dataset.s3.amazonaws.com/validation/{image_id}.jpg"
USER_AGENT = "SORT-RAC-target-expansion/1.0 (educational waste-classification dataset)"
TARGETS = {
    "pen_marker": {"Pen"},
    "light_bulb": {"Light bulb"},
    "disposable_cutlery": {"Spoon", "Fork", "Chopsticks"},
    "plastic_cosmetic_container": {"Cosmetics"},
}


def download_metadata(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 1000:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=180, stream=True) as response:
        response.raise_for_status()
        with destination.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                output.write(chunk)


def relative_area(row: dict[str, str]) -> float:
    return (float(row["XMax"]) - float(row["XMin"])) * (float(row["YMax"]) - float(row["YMin"]))


def crop_box(image: Image.Image, row: dict[str, str]) -> Image.Image | None:
    x1 = float(row["XMin"]) * image.width
    x2 = float(row["XMax"]) * image.width
    y1 = float(row["YMin"]) * image.height
    y2 = float(row["YMax"]) * image.height
    padding = max(x2 - x1, y2 - y1) * 0.22
    crop = image.crop(
        (
            max(0, int(x1 - padding)),
            max(0, int(y1 - padding)),
            min(image.width, int(x2 + padding)),
            min(image.height, int(y2 + padding)),
        )
    )
    if min(crop.size) < 112 or max(crop.size) / min(crop.size) > 5:
        return None
    return crop


def download_candidate(candidate: dict[str, object]) -> dict[str, object] | None:
    image_id = str(candidate["image_id"])
    source_url = IMAGE_URL.format(image_id=image_id)
    try:
        response = requests.get(source_url, headers={"User-Agent": USER_AGENT}, timeout=(10, 45))
        response.raise_for_status()
        image = ImageOps.exif_transpose(Image.open(BytesIO(response.content))).convert("RGB")
        crop = crop_box(image, candidate["row"])
    except (requests.RequestException, UnidentifiedImageError, OSError):
        return None
    if crop is None:
        return None
    crop.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    crop.save(buffer, "JPEG", quality=92, optimize=True)
    payload = buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    class_name = str(candidate["class"])
    destination = CANDIDATE_ROOT / class_name / f"openimages_expansion_{image_id}_{digest[:12]}.jpg"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {
        "class": class_name,
        "sourceClass": candidate["display_name"],
        "imageId": image_id,
        "sourceUrl": source_url,
        "sourcePage": "https://storage.googleapis.com/openimages/web/index.html",
        "license": "CC BY 2.0",
        "path": destination.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "review": "candidate_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-class", type=int, default=60)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    classes_path = CACHE / "classes.csv"
    boxes_path = CACHE / "validation.csv"
    download_metadata(CLASSES_URL, classes_path)
    download_metadata(BOXES_URL, boxes_path)
    display_by_mid = {
        row["LabelName"]: row["DisplayName"]
        for row in csv.DictReader(classes_path.open(encoding="utf-8"))
    }
    target_by_name = {display: class_name for class_name, displays in TARGETS.items() for display in displays}
    candidates: dict[str, list[dict[str, object]]] = {name: [] for name in TARGETS}
    used_images: set[str] = set()
    with boxes_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    rows.sort(key=lambda row: hashlib.sha256(f"target-expansion:{row['ImageID']}".encode()).hexdigest())
    for row in rows:
        image_id = row["ImageID"]
        display_name = display_by_mid.get(row["LabelName"])
        class_name = target_by_name.get(display_name or "")
        if (
            class_name is None
            or image_id in used_images
            or len(candidates[class_name]) >= args.per_class
            or row.get("IsDepiction") == "1"
            or row.get("IsInside") == "1"
            or row.get("IsGroupOf") == "1"
            or relative_area(row) < 0.015
        ):
            continue
        candidates[class_name].append(
            {"class": class_name, "display_name": display_name, "image_id": image_id, "row": row}
        )
        used_images.add(image_id)

    work = [candidate for values in candidates.values() for candidate in values]
    records: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(download_candidate, candidate) for candidate in work]
        for index, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            if record:
                records.append(record)
            if index % 25 == 0 or index == len(futures):
                print(f"Processed {index}/{len(futures)}; kept {len(records)}", flush=True)

    records.sort(key=lambda row: (str(row["class"]), str(row["path"])))
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    for class_name in TARGETS:
        count = sum(record["class"] == class_name for record in records)
        print(f"{class_name:<16} {count:>3}")
    print(f"Candidate manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
