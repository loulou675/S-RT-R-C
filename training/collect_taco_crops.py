"""Add single-object crops from TACO's real-world litter photographs.

TACO contains photos taken in woods, roads, beaches, and other everyday
settings. Its COCO annotations let us crop one labeled object from a cluttered
scene, giving the classifier realistic backgrounds while keeping one item per
candidate image. The original Flickr page is logged for every crop; check the
source terms before redistributing a trained model.
"""

from __future__ import annotations

import json
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "training" / "dataset" / "train"
SOURCES_PATH = ROOT / "training" / "taco-field-sources.jsonl"
ANNOTATIONS_URL = "https://raw.githubusercontent.com/pedropro/TACO/master/data/annotations.json"
USER_AGENT = "sort-rac-local-taco-collector/1.0 (single-item research prototype)"

CLASS_MAP = {
    "Battery": "battery",
    "Paper cup": "paper_cup",
    "Disposable plastic cup": "plastic_takeaway_cup",
    "Clear plastic bottle": "plastic_water_bottle",
    "Other plastic bottle": "plastic_water_bottle",
    # TACO's Food waste category is intentionally a review bucket: it can
    # contain peels as well as other food scraps.
    "Food waste": "fruit_peel",
}

TARGET_TOTALS = {"plastic_water_bottle": 25}


def get_json(url: str) -> dict:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    return response.json()


def existing_keys() -> set[str]:
    if not SOURCES_PATH.exists():
        return set()
    keys = set()
    for line in SOURCES_PATH.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line).get("key")
            if isinstance(value, str):
                keys.add(value)
        except json.JSONDecodeError:
            pass
    return keys


def main() -> None:
    dataset = get_json(ANNOTATIONS_URL)
    categories = {item["id"]: item["name"] for item in dataset["categories"]}
    images = {item["id"]: item for item in dataset["images"]}
    by_class: dict[str, list[dict]] = {name: [] for name in CLASS_MAP.values()}
    for annotation in dataset["annotations"]:
        source_class = categories.get(annotation.get("category_id"))
        target_class = CLASS_MAP.get(source_class)
        image = images.get(annotation.get("image_id"))
        if not target_class or not image or len(annotation.get("bbox", [])) != 4:
            continue
        by_class[target_class].append({"annotation": annotation, "image": image, "source_class": source_class})

    seen = existing_keys()
    with requests.Session() as session, SOURCES_PATH.open("a", encoding="utf-8") as log:
        for target_class, candidates in by_class.items():
            destination = DATASET_ROOT / target_class
            destination.mkdir(parents=True, exist_ok=True)
            existing_count = len(list(destination.glob("taco_field_*.jpg")))
            remaining = max(0, TARGET_TOTALS.get(target_class, 10) - existing_count)
            if remaining == 0:
                print(f"{target_class}: already has {existing_count} TACO candidates", flush=True)
                continue
            added = 0
            # Deterministic ordering makes reruns resumable and review batches stable.
            for candidate in candidates:
                if added >= remaining:
                    break
                annotation = candidate["annotation"]
                image_meta = candidate["image"]
                key = f"v2:{image_meta['id']}:{annotation['id']}"
                if key in seen:
                    continue
                url = image_meta.get("flickr_640_url") or image_meta.get("flickr_url")
                if not url:
                    continue
                try:
                    response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=(10, 20))
                    response.raise_for_status()
                    image = Image.open(BytesIO(response.content)).convert("RGB")
                    x, y, w, h = (float(value) for value in annotation["bbox"])
                    if w <= 0 or h <= 0:
                        continue
                    # TACO bboxes use the original image dimensions, while
                    # flickr_640_url is resized. Scale before cropping.
                    scale_x = image.width / float(image_meta.get("width", image.width))
                    scale_y = image.height / float(image_meta.get("height", image.height))
                    x, w = x * scale_x, w * scale_x
                    y, h = y * scale_y, h * scale_y
                    pad = 0.12 * max(w, h)
                    left = max(0, int(x - pad))
                    top = max(0, int(y - pad))
                    right = min(image.width, int(x + w + pad))
                    bottom = min(image.height, int(y + h + pad))
                    crop = image.crop((left, top, right, bottom))
                    if min(crop.size) < 96:
                        continue
                except Exception as error:  # noqa: BLE001 - skip blocked/broken media
                    print(f"{target_class}: skip image {image_meta['id']}: {error}", flush=True)
                    continue
                output = destination / f"taco_field_v2_{image_meta['id']}_{annotation['id']}.jpg"
                crop.save(output, format="JPEG", quality=92, optimize=True)
                record = {
                    "key": key,
                    "class": target_class,
                    "source_class": candidate["source_class"],
                    "local_file": str(output.relative_to(ROOT)),
                    "source_image_id": image_meta["id"],
                    "annotation_id": annotation["id"],
                    "flickr_url": image_meta.get("flickr_url"),
                    "flickr_640_url": image_meta.get("flickr_640_url"),
                    "dataset_repo": "https://github.com/pedropro/TACO",
                    "dataset_license": "MIT for the dataset code/metadata; verify the original Flickr image terms",
                }
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
                log.flush()
                seen.add(key)
                added += 1
                print(f"{target_class}: added {output.name}", flush=True)
                time.sleep(0.2)
            print(f"{target_class}: added {added} TACO candidate crops", flush=True)


if __name__ == "__main__":
    main()
