"""Add close-up training views for small component boxes in a YOLO dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--scale", type=float, default=3.0)
    parser.add_argument("--splits", nargs="+", default=["train"])
    args = parser.parse_args()

    created = 0
    for split in args.splits:
        image_dir = args.dataset / "images" / split
        label_dir = args.dataset / "labels" / split
        for image_path in sorted(image_dir.glob("*.jpg")):
            if "_detail_" in image_path.stem:
                continue
            label_path = label_dir / f"{image_path.stem}.txt"
            lines = [line for line in label_path.read_text().splitlines() if line.strip()]
            if not lines:
                continue
            with Image.open(image_path) as source:
                image = source.convert("RGB")
                width, height = image.size
                for index, line in enumerate(lines):
                    class_id, center_x, center_y, box_width, box_height = line.split()
                    center_x = float(center_x) * width
                    center_y = float(center_y) * height
                    box_width = float(box_width) * width
                    box_height = float(box_height) * height
                    crop_size = min(max(box_width, box_height) * args.scale, width, height)
                    if crop_size >= min(width, height) * 0.92:
                        continue
                    left = clamp(center_x - crop_size / 2, 0, width - crop_size)
                    top = clamp(center_y - crop_size / 2, 0, height - crop_size)
                    detail = image.crop((round(left), round(top), round(left + crop_size), round(top + crop_size)))
                    stem = f"{image_path.stem}_detail_{index}"
                    detail.save(image_dir / f"{stem}.jpg", format="JPEG", quality=92, optimize=True)
                    adjusted_x = (center_x - left) / crop_size
                    adjusted_y = (center_y - top) / crop_size
                    adjusted_width = box_width / crop_size
                    adjusted_height = box_height / crop_size
                    (label_dir / f"{stem}.txt").write_text(
                        f"{class_id} {adjusted_x:.6f} {adjusted_y:.6f} {adjusted_width:.6f} {adjusted_height:.6f}\n",
                        encoding="utf-8",
                    )
                    created += 1

    print(f"Created {created} close-up component samples.")


if __name__ == "__main__":
    main()
