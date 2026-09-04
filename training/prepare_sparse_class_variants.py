#!/usr/bin/env python3
"""Create conservative train-only variants for the four sparse 40-class outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CLASSES = ("hair_clip", "hair_tie", "pen_marker", "phone_case")
EXTRA_ACCEPTED = {
    "hair_clip": ("commons_hair_clip_28bb18b0c0184a3c.jpg",),
    "hair_tie": (),
    "pen_marker": (
        "commons_pen_marker_103f541f07a8e02f.jpg",
        "commons_pen_marker_33fadf26c6cf7756.jpg",
        "commons_pen_marker_e5788929093fd048.jpg",
    ),
    "phone_case": ("commons_phone_case_79bc2f6c171622e3.jpg",),
}
EXTERNAL_ACCEPTED = {
    "hair_clip": (),
    "hair_tie": (),
    "pen_marker": (),
    "phone_case": (
        "roboflow_phone_case_v1/phone_case/train_20kEqS8qFyBsrDcUEOGl.jpg",
        "roboflow_phone_case_v1/phone_case/train_47iyIiXFPNCrYyyUY9TJ.jpg",
        "roboflow_phone_case_v1/phone_case/train_ALtBeQCLyWhMU9d0mvuJ.jpg",
    ),
}


def fill_color(image: Image.Image) -> tuple[int, int, int]:
    reduced = image.resize((1, 1), Image.Resampling.BILINEAR)
    return tuple(int(channel) for channel in reduced.getpixel((0, 0)))


def zoom_out(image: Image.Image, factor: float) -> Image.Image:
    width, height = image.size
    resized = image.resize(
        (max(1, int(width * factor)), max(1, int(height * factor))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", image.size, fill_color(image))
    canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return canvas


def variant(image: Image.Image, index: int) -> Image.Image:
    fill = fill_color(image)
    if index == 0:
        return image.rotate(-8, Image.Resampling.BICUBIC, expand=False, fillcolor=fill)
    if index == 1:
        return image.rotate(8, Image.Resampling.BICUBIC, expand=False, fillcolor=fill)
    if index == 2:
        return ImageEnhance.Brightness(image).enhance(0.82)
    if index == 3:
        return ImageEnhance.Brightness(image).enhance(1.16)
    if index == 4:
        return ImageEnhance.Contrast(image).enhance(1.18)
    if index == 5:
        return image.filter(ImageFilter.GaussianBlur(0.65))
    if index == 6:
        return zoom_out(image, 0.82)
    if index == 7:
        return ImageOps.mirror(image)
    raise ValueError(index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing expansion: {output}")

    records: list[dict[str, object]] = []
    for class_name in CLASSES:
        source_paths = sorted(
            path
            for path in (ROOT / "training/classifier_dataset/train" / class_name).glob("*")
            if path.is_file() and not path.name.startswith("oversample_")
        )
        source_paths.extend(
            ROOT / "training/candidate_dataset/new_items" / class_name / filename
            for filename in EXTRA_ACCEPTED[class_name]
        )
        source_paths.extend(
            ROOT / "training/external_sources" / relative_path
            for relative_path in EXTERNAL_ACCEPTED[class_name]
        )
        variant_count = 8 if class_name in {"hair_tie", "phone_case"} else 3
        destination_dir = output / class_name
        destination_dir.mkdir(parents=True, exist_ok=True)
        for source in source_paths:
            with Image.open(source) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
            for index in range(variant_count):
                transformed = variant(image, index)
                destination = destination_dir / (
                    f"expansion_aug_{class_name}_{source_digest[:12]}_{index}.jpg"
                )
                transformed.save(destination, "JPEG", quality=91, optimize=True)
                records.append(
                    {
                        "class": class_name,
                        "source": source.relative_to(ROOT).as_posix(),
                        "variant": index,
                        "destination": destination.relative_to(ROOT).as_posix(),
                        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                    }
                )

    (output / "manifest.json").write_text(
        json.dumps({"records": records}, indent=2) + "\n", encoding="utf-8"
    )
    for class_name in CLASSES:
        count = sum(record["class"] == class_name for record in records)
        print(f"{class_name:<12} variants={count:>3}")
    print(f"Created {len(records)} train-only variants at {output}")


if __name__ == "__main__":
    main()
