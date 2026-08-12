"""Create compact contact sheets for manual class-label review."""

from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def stable_sample(paths: list[Path], limit: int) -> list[Path]:
    return sorted(paths, key=lambda path: hashlib.sha256(path.name.encode()).hexdigest())[:limit]


def make_sheet(class_name: str, files: list[Path], output: Path, columns: int = 5) -> None:
    thumb_width, thumb_height, label_height = 190, 150, 36
    rows = (len(files) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_width, 44 + rows * (thumb_height + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=13)
    draw.text((12, 12), f"{class_name} ({len(files)} review samples)", fill="black", font=font)
    for index, path in enumerate(files):
        x = (index % columns) * thumb_width
        y = 44 + (index // columns) * (thumb_height + label_height)
        try:
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                fitted = ImageOps.contain(image, (thumb_width - 12, thumb_height - 12))
        except Exception:  # noqa: BLE001 - damaged files stay visible as a blank tile
            fitted = Image.new("RGB", (thumb_width - 12, thumb_height - 12), "#ffdddd")
        sheet.paste(fitted, (x + (thumb_width - fitted.width) // 2, y + (thumb_height - fitted.height) // 2))
        label = "\n".join(textwrap.wrap(path.stem, width=25)[:2])
        draw.text((x + 6, y + thumb_height + 2), label, fill="#222222", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="JPEG", quality=88, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "training" / "dataset" / "train")
    parser.add_argument("--output", type=Path, default=ROOT / "training" / "review_sheets")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--prefix", default="", help="Only include filenames with this prefix")
    args = parser.parse_args()

    classes = json.loads((ROOT / "training" / "classes.json").read_text(encoding="utf-8"))["classes"]
    for class_name in classes:
        folder = args.data / class_name
        files = [
            path
            for path in folder.glob("**/*")
            if path.suffix.lower() in IMAGE_EXTENSIONS and path.name.startswith(args.prefix)
        ]
        selected = stable_sample(files, args.samples)
        if not selected:
            continue
        output = args.output / f"{class_name}.jpg"
        make_sheet(class_name, selected, output)
        try:
            print(output.relative_to(ROOT))
        except ValueError:
            print(output)


if __name__ == "__main__":
    main()
