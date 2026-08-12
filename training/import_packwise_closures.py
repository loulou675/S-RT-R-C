#!/usr/bin/env python3
"""Create a YOLO closure dataset from PackWISE plastic-lid annotations."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = Path("/tmp/PackWISE_dataset_v2.zip")
DEFAULT_OUTPUT = ROOT / "training" / "packwise_component_closure"


def bounded_crop(image_width: int, image_height: int, bbox: list[float]) -> tuple[float, float, float, float]:
    x, y, width, height = bbox
    side = min(max(max(width, height) * 6.0, 512.0), 1400.0, float(image_width), float(image_height))
    center_x, center_y = x + width / 2, y + height / 2
    left = min(max(center_x - side / 2, 0.0), image_width - side)
    top = min(max(center_y - side / 2, 0.0), image_height - side)
    return left, top, left + side, top + side


def adjusted_label(bbox: list[float], crop: tuple[float, float, float, float]) -> str | None:
    x, y, width, height = bbox
    left, top, right, bottom = crop
    center_x, center_y = x + width / 2, y + height / 2
    if not (left <= center_x <= right and top <= center_y <= bottom):
        return None
    crop_width, crop_height = right - left, bottom - top
    return (
        f"0 {(center_x - left) / crop_width:.6f} {(center_y - top) / crop_height:.6f} "
        f"{min(width / crop_width, 1.0):.6f} {min(height / crop_height, 1.0):.6f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {output}")

    split_counts: dict[str, int] = {}
    with zipfile.ZipFile(args.archive) as archive:
        for split in ("train", "val", "test"):
            coco = json.loads(archive.read(f"data/{split}.json"))
            categories = {entry["id"]: entry["name"] for entry in coco["categories"]}
            images = {entry["id"]: entry for entry in coco["images"]}
            lids_by_image: dict[int, list[dict]] = defaultdict(list)
            for annotation in coco["annotations"]:
                if categories.get(annotation["category_id"]) == "plastic-lid" and not annotation.get("iscrowd", 0):
                    lids_by_image[annotation["image_id"]].append(annotation)

            image_dir = output / "images" / split
            label_dir = output / "labels" / split
            image_dir.mkdir(parents=True, exist_ok=True)
            label_dir.mkdir(parents=True, exist_ok=True)
            created = 0
            for image_id, annotations in sorted(lids_by_image.items()):
                metadata = images[image_id]
                with Image.open(io.BytesIO(archive.read(f"data/{split}/{metadata['file_name']}"))) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                    for target in annotations:
                        crop_box = bounded_crop(image.width, image.height, target["bbox"])
                        labels = [adjusted_label(annotation["bbox"], crop_box) for annotation in annotations]
                        labels = [label for label in labels if label]
                        if not labels:
                            continue
                        crop = image.crop(tuple(round(value) for value in crop_box))
                        crop.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                        digest = hashlib.sha256(f"{split}:{target['id']}".encode()).hexdigest()[:16]
                        stem = f"packwise_lid_{digest}"
                        crop.save(image_dir / f"{stem}.jpg", "JPEG", quality=92, optimize=True)
                        (label_dir / f"{stem}.txt").write_text("\n".join(labels) + "\n", encoding="utf-8")
                        created += 1
            split_counts[split] = created

    (output / "data.yaml").write_text(
        f"path: {output}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: closure\n",
        encoding="utf-8",
    )
    print(json.dumps(split_counts, indent=2))


if __name__ == "__main__":
    main()
