"""Import reviewed real photos into the local YOLO component dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CLASS_IDS = {"closure": 0, "food": 1, "straw": 2}
VALID_SPLITS = {"train", "val", "test"}
PREFIX = "real_component_"
HEIC_SUFFIXES = {".heic", ".heif"}


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned[:48] or "image"


def validate_box(box: dict, source: str) -> None:
    if box.get("class") not in CLASS_IDS:
        raise ValueError(f"Unknown class in {source}: {box.get('class')}")
    values = box.get("xywhn")
    if not isinstance(values, list) or len(values) != 4:
        raise ValueError(f"Invalid xywhn in {source}: {values}")
    cx, cy, width, height = (float(value) for value in values)
    if not all(0.0 <= value <= 1.0 for value in (cx, cy, width, height)):
        raise ValueError(f"Out-of-range box in {source}: {values}")
    if width <= 0.0 or height <= 0.0:
        raise ValueError(f"Empty box in {source}: {values}")
    if cx - width / 2 < 0 or cy - height / 2 < 0 or cx + width / 2 > 1 or cy + height / 2 > 1:
        raise ValueError(f"Box crosses image bounds in {source}: {values}")


def load_rgb_image(source: Path) -> Image.Image:
    """Open common image formats and convert HEIC/HEIF through macOS sips."""
    if source.suffix.lower() not in HEIC_SUFFIXES:
        with Image.open(source) as raw_image:
            return ImageOps.exif_transpose(raw_image).convert("RGB")

    with tempfile.TemporaryDirectory(prefix="sort-rac-heic-") as directory:
        converted = Path(directory) / f"{source.stem}.jpg"
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(source), "--out", str(converted)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with Image.open(converted) as raw_image:
            return ImageOps.exif_transpose(raw_image).convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "training" / "real_component_annotations.json",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "training" / "component_dataset",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("classes") != ["closure", "food", "straw"]:
        raise SystemExit("Manifest class order must be ['closure', 'food', 'straw'].")

    for split in VALID_SPLITS:
        image_dir = args.dataset / "images" / split
        label_dir = args.dataset / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        for old_path in image_dir.glob(f"{PREFIX}*"):
            old_path.unlink()
        for old_path in label_dir.glob(f"{PREFIX}*"):
            old_path.unlink()

    class_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    negative_count = 0
    imported_records: list[dict] = []

    for record in manifest["records"]:
        source_text = record["source"]
        source = ROOT / source_text
        split = record.get("split", "train")
        boxes = record.get("boxes", [])
        if split not in VALID_SPLITS:
            raise ValueError(f"Invalid split in {source_text}: {split}")
        if not source.is_file():
            raise FileNotFoundError(source)
        for box in boxes:
            validate_box(box, source_text)

        digest = hashlib.sha1(source_text.encode("utf-8")).hexdigest()[:10]
        stem = f"{PREFIX}{safe_name(record.get('group', source.parent.name))}_{safe_name(source.stem)}_{digest}"
        image_path = args.dataset / "images" / split / f"{stem}.jpg"
        label_path = args.dataset / "labels" / split / f"{stem}.txt"

        image = load_rgb_image(source)
        image.save(image_path, format="JPEG", quality=95, optimize=True)
        image.close()

        lines = []
        for box in boxes:
            class_name = box["class"]
            class_counts[class_name] += 1
            values = " ".join(f"{float(value):.6f}" for value in box["xywhn"])
            lines.append(f"{CLASS_IDS[class_name]} {values}")
        label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        split_counts[split] += 1
        negative_count += int(not boxes)
        imported_records.append(
            {
                "source": source_text,
                "dataset_image": str(image_path.relative_to(ROOT)),
                "dataset_label": str(label_path.relative_to(ROOT)),
                "split": split,
                "group": record.get("group"),
                "boxes": boxes,
            }
        )

    output_manifest = ROOT / "training" / "source_manifests" / "real-component-import.json"
    output_manifest.write_text(
        json.dumps(
            {
                "source_manifest": str(args.manifest.relative_to(ROOT)),
                "records": imported_records,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Imported {sum(split_counts.values())} real component images: {dict(split_counts)}")
    print(f"Boxes: {dict(class_counts)}; negative images: {negative_count}")
    print(f"Wrote reproducibility manifest: {output_manifest}")


if __name__ == "__main__":
    main()
