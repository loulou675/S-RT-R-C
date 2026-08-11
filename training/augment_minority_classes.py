"""Create conservative single-item augmentations for undersized train classes."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


ROOT = Path(__file__).resolve().parents[1]
TRAIN_ROOT = ROOT / "training" / "dataset_curated" / "train"
SEED = 20260805


def augment(image: Image.Image, rng: random.Random) -> Image.Image:
    result = image.convert("RGB")
    if rng.random() < 0.5:
        result = ImageOps.mirror(result)
    if rng.random() < 0.8:
        result = result.rotate(rng.uniform(-12, 12), resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(238, 238, 238))
    if rng.random() < 0.9:
        result = ImageEnhance.Brightness(result).enhance(rng.uniform(0.86, 1.14))
        result = ImageEnhance.Contrast(result).enhance(rng.uniform(0.88, 1.16))
        result = ImageEnhance.Color(result).enhance(rng.uniform(0.9, 1.1))
    width, height = result.size
    scale = rng.uniform(0.88, 1.0)
    crop_width, crop_height = max(32, int(width * scale)), max(32, int(height * scale))
    left = rng.randint(0, max(0, width - crop_width))
    top = rng.randint(0, max(0, height - crop_height))
    return result.crop((left, top, left + crop_width, top + crop_height)).resize((224, 224), Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=60, help="Balanced train images per class after augmentation")
    args = parser.parse_args()
    rng = random.Random(SEED)
    for class_dir in sorted(TRAIN_ROOT.iterdir()):
        if not class_dir.is_dir():
            continue
        originals = sorted(path for path in class_dir.glob("*.jpg") if not path.name.startswith("aug_"))
        if not originals or len(list(class_dir.glob("*.jpg"))) >= args.target:
            continue

        existing = len(list(class_dir.glob("*.jpg")))
        index = 0
        while existing < args.target:
            source = originals[index % len(originals)]
            with Image.open(source) as image:
                output = class_dir / f"aug_{index:03d}_{source.stem}.jpg"
                augment(image, rng).save(output, format="JPEG", quality=90, optimize=True)
            existing += 1
            index += 1
        print(f"{class_dir.name}: {existing} train images")


if __name__ == "__main__":
    main()
