#!/usr/bin/env python3
"""Collect train-only TACO candidates for weak SORT RAC item classes.

The collector deliberately selects source image IDs that are absent from the
existing TACO manifest. It writes review candidates first; a human must inspect
the contact sheets before the files are imported into classifier training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ROOT = ROOT / "training" / "candidate_dataset" / "target_expansion" / "taco"
MANIFEST = ROOT / "training" / "source_manifests" / "taco-expansion-candidates.jsonl"
EXISTING_MANIFEST = ROOT / "training" / "source_manifests" / "taco-field-sources.jsonl"
ANNOTATIONS_URL = "https://raw.githubusercontent.com/pedropro/TACO/master/data/annotations.json"
SOURCE_PAGE = "https://github.com/pedropro/TACO"
USER_AGENT = "SORT-RAC-target-expansion/1.0 (educational waste-classification dataset)"

TARGETS = {
    "aerosol_can": {"Aerosol"},
    "aluminium_drink_can": {"Drink can"},
    "battery": {"Battery"},
    "food_waste": {"Food waste"},
    "paper_bag": {"Paper bag", "Plastified paper bag"},
    "paper_cup": {"Paper cup"},
    "plastic_cup_lid": {"Plastic lid"},
    "plastic_food_container": {
        "Disposable food container",
        "Other plastic container",
        "Tupperware",
    },
    "styrofoam_container": {"Foam cup", "Foam food container"},
    "tissue": {"Tissues"},
    "plastic_takeaway_cup": {"Disposable plastic cup"},
    "drink_carton": {"Drink carton"},
    "snack_wrapper": {"Crisp packet", "Other plastic wrapper"},
    "paperboard_packaging": {"Other carton", "Meal carton", "Egg carton"},
}


def crop_box(image: Image.Image, bbox: list[float], source_size: tuple[int, int]) -> Image.Image | None:
    source_width, source_height = source_size
    scale_x = image.width / source_width
    scale_y = image.height / source_height
    x, y, width, height = bbox
    x *= scale_x
    y *= scale_y
    width *= scale_x
    height *= scale_y
    padding = max(width, height) * 0.22
    box = (
        max(0, int(x - padding)),
        max(0, int(y - padding)),
        min(image.width, int(x + width + padding)),
        min(image.height, int(y + height + padding)),
    )
    crop = image.crop(box)
    if min(crop.size) < 112 or max(crop.size) / min(crop.size) > 4.5:
        return None
    return crop


def download_candidate(candidate: dict[str, object]) -> dict[str, object] | None:
    image_record = candidate["image"]
    assert isinstance(image_record, dict)
    urls = [image_record.get("flickr_url"), image_record.get("flickr_640_url")]
    image = None
    source_url = None
    for url in urls:
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(10, 45))
            response.raise_for_status()
            image = ImageOps.exif_transpose(Image.open(BytesIO(response.content))).convert("RGB")
            source_url = url
            break
        except (requests.RequestException, UnidentifiedImageError, OSError):
            continue
    if image is None or source_url is None:
        return None

    crop = crop_box(
        image,
        candidate["bbox"],
        (int(image_record["width"]), int(image_record["height"])),
    )
    if crop is None:
        return None
    crop.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    crop.save(buffer, "JPEG", quality=92, optimize=True)
    payload = buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    class_name = str(candidate["class"])
    annotation_id = int(candidate["annotation_id"])
    destination = CANDIDATE_ROOT / class_name / f"taco_expansion_{annotation_id}_{digest[:12]}.jpg"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {
        "class": class_name,
        "sourceClass": candidate["source_class"],
        "sourceImageId": int(image_record["id"]),
        "annotationId": annotation_id,
        "sourceUrl": source_url,
        "flickrOriginal": image_record.get("flickr_url"),
        "flickr640": image_record.get("flickr_640_url"),
        "datasetPage": SOURCE_PAGE,
        "datasetLicense": "MIT for TACO code/metadata; original Flickr image terms require review",
        "path": destination.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "review": "candidate_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-class", type=int, default=35)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    response = requests.get(ANNOTATIONS_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    payload = response.json()
    categories = {int(row["id"]): str(row["name"]) for row in payload["categories"]}
    images = {int(row["id"]): row for row in payload["images"]}

    used_image_ids: set[int] = set()
    existing_records: list[dict[str, object]] = []
    if EXISTING_MANIFEST.exists():
        for line in EXISTING_MANIFEST.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                used_image_ids.add(int(record.get("source_image_id")))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
    if MANIFEST.exists():
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                existing_records.append(record)
                used_image_ids.add(int(record.get("sourceImageId")))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    candidates: dict[str, list[dict[str, object]]] = {name: [] for name in TARGETS}
    selected_images = set(used_image_ids)
    annotations = sorted(
        payload["annotations"],
        key=lambda row: hashlib.sha256(f"taco-expansion:{row['id']}".encode()).hexdigest(),
    )
    for annotation in annotations:
        image_id = int(annotation["image_id"])
        if image_id in selected_images or int(annotation.get("iscrowd", 0)):
            continue
        source_class = categories[int(annotation["category_id"])]
        target_class = next((name for name, labels in TARGETS.items() if source_class in labels), None)
        if target_class is None or len(candidates[target_class]) >= args.per_class:
            continue
        bbox = annotation["bbox"]
        image_record = images[image_id]
        relative_area = (float(bbox[2]) * float(bbox[3])) / (
            float(image_record["width"]) * float(image_record["height"])
        )
        if relative_area < 0.012:
            continue
        candidates[target_class].append(
            {
                "class": target_class,
                "source_class": source_class,
                "annotation_id": int(annotation["id"]),
                "bbox": bbox,
                "image": image_record,
            }
        )
        selected_images.add(image_id)

    work = [candidate for class_candidates in candidates.values() for candidate in class_candidates]
    records: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(download_candidate, candidate) for candidate in work]
        for index, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            if record:
                records.append(record)
            if index % 25 == 0 or index == len(futures):
                print(f"Processed {index}/{len(futures)}; kept {len(records)}", flush=True)

    merged_by_hash = {
        str(record["sha256"]): record
        for record in existing_records + records
        if record.get("sha256")
    }
    records = sorted(
        merged_by_hash.values(),
        key=lambda row: (str(row["class"]), str(row["path"])),
    )
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    for class_name in TARGETS:
        count = sum(record["class"] == class_name for record in records)
        print(f"{class_name:<25} {count:>3}")
    print(f"Candidate manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
