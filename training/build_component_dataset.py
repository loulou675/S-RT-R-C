"""Build a YOLO component-detection dataset from reviewed TACO boxes.

This creates a conservative baseline for visible packaging parts. Classes that
cannot be inferred reliably from an ordinary photo remain rule-only and are not
included in this generated detector dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS_URL = "https://raw.githubusercontent.com/pedropro/TACO/master/data/annotations.json"
USER_AGENT = "sort-rac-component-dataset/1.0"
SOURCE_TO_COMPONENT = {
    "Clear plastic bottle": "bottle_body",
    "Other plastic bottle": "bottle_body",
    "Glass bottle": "bottle_body",
    "Drink can": "can_body",
    "Food Can": "can_body",
    "Aerosol": "can_body",
    "Drink carton": "carton_body",
    "Meal carton": "carton_body",
    "Disposable plastic cup": "cup_body",
    "Paper cup": "cup_body",
    "Foam cup": "cup_body",
    "Other plastic cup": "cup_body",
    "Metal bottle cap": "closure",
    "Metal lid": "closure",
    "Plastic bottle cap": "closure",
    "Plastic lid": "closure",
    "Plastic straw": "straw",
    "Paper straw": "straw",
}


def stable_split(image_id: int) -> str:
    bucket = int(hashlib.sha256(f"sort-rac:{image_id}".encode()).hexdigest()[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "val"
    return "test"


def fetch_json(url: str) -> dict:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    return response.json()


def download_image(image_meta: dict) -> tuple[Image.Image, str] | None:
    urls = [image_meta.get("flickr_640_url"), image_meta.get("flickr_url")]
    for url in (value for value in urls if value):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(10, 35))
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGB"), url
        except (requests.RequestException, UnidentifiedImageError, OSError):
            continue
    return None


def prepare_one(
    image_meta: dict,
    annotations: list[dict],
    names: list[str],
    output: Path,
    allow_empty: bool = False,
) -> dict | None:
    downloaded = download_image(image_meta)
    if not downloaded:
        return None
    image, source_url = downloaded
    source_width = float(image_meta.get("width") or image.width)
    source_height = float(image_meta.get("height") or image.height)
    split = stable_split(int(image_meta["id"]))
    labels: list[str] = []
    counts: Counter[str] = Counter()

    for annotation in annotations:
        code = annotation["component_code"]
        x, y, width, height = (float(value) for value in annotation["bbox"])
        x *= image.width / source_width
        width *= image.width / source_width
        y *= image.height / source_height
        height *= image.height / source_height
        x = max(0.0, min(float(image.width), x))
        y = max(0.0, min(float(image.height), y))
        width = max(0.0, min(float(image.width) - x, width))
        height = max(0.0, min(float(image.height) - y, height))
        if width < 4 or height < 4 or width * height < 36:
            continue
        center_x = (x + width / 2) / image.width
        center_y = (y + height / 2) / image.height
        labels.append(f"{names.index(code)} {center_x:.6f} {center_y:.6f} {width / image.width:.6f} {height / image.height:.6f}")
        counts[code] += 1

    if not labels and not allow_empty:
        return None
    stem = f"taco_{int(image_meta['id']):05d}"
    image_path = output / "images" / split / f"{stem}.jpg"
    label_path = output / "labels" / split / f"{stem}.txt"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(image_path, format="JPEG", quality=92, optimize=True)
    label_path.write_text("\n".join(labels) + "\n", encoding="utf-8")
    return {
        "image_id": image_meta["id"],
        "split": split,
        "source_url": source_url,
        "image": str(image_path.relative_to(ROOT)),
        "labels": dict(counts),
        "negative": not labels,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "training" / "component_dataset")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--negative-images", type=int, default=0)
    parser.add_argument("--model-classes", nargs="+")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        if not args.overwrite:
            raise SystemExit(f"Output already exists: {output}. Pass --overwrite to rebuild it.")
        shutil.rmtree(output)

    config = json.loads((ROOT / "training" / "component_classes.json").read_text(encoding="utf-8"))
    names = args.model_classes or config["modelClasses"]
    dataset = fetch_json(ANNOTATIONS_URL)
    categories = {item["id"]: item["name"] for item in dataset["categories"]}
    images = {item["id"]: item for item in dataset["images"]}
    by_image: dict[int, list[dict]] = defaultdict(list)
    for annotation in dataset["annotations"]:
        component_code = SOURCE_TO_COMPONENT.get(categories.get(annotation.get("category_id")))
        if component_code in names and len(annotation.get("bbox", [])) == 4:
            by_image[int(annotation["image_id"])].append({**annotation, "component_code": component_code})

    negative_ids = sorted(
        (image_id for image_id in images if image_id not in by_image),
        key=lambda image_id: hashlib.sha256(f"negative:{image_id}".encode()).hexdigest(),
    )[: max(0, args.negative_images)]

    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(prepare_one, images[image_id], annotations, names, output): image_id
            for image_id, annotations in by_image.items()
        }
        futures.update(
            {
                executor.submit(prepare_one, images[image_id], [], names, output, True): image_id
                for image_id in negative_ids
            }
        )
        for index, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            if record:
                records.append(record)
            if index % 100 == 0 or index == len(futures):
                print(f"Processed {index}/{len(futures)} source images; kept {len(records)}", flush=True)

    records.sort(key=lambda item: int(item["image_id"]))
    split_counts: Counter[str] = Counter(record["split"] for record in records)
    class_counts: dict[str, Counter[str]] = {split: Counter() for split in ("train", "val", "test")}
    for record in records:
        class_counts[record["split"]].update(record["labels"])

    output.mkdir(parents=True, exist_ok=True)
    yaml_lines = [f"path: {output}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    yaml_lines.extend(f"  {index}: {name}" for index, name in enumerate(names))
    (output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    summary = {
        "source": ANNOTATIONS_URL,
        "images": dict(split_counts),
        "boxes": {split: dict(class_counts[split]) for split in class_counts},
        "classes": names,
        "negativeImages": sum(1 for record in records if record["negative"]),
        "records": records,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"images": summary["images"], "boxes": summary["boxes"]}, indent=2))


if __name__ == "__main__":
    main()
