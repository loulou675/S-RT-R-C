"""Validate a dataset folder against the frontend's accepted image formats.

The app accepts JPEG, PNG, and WebP uploads. Unsupported or unreadable files
are moved to a reversible quarantine; decodable unsupported images are also
re-encoded as JPEG so the usable copy remains in the class folder.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp", ".tif", ".tiff"}


def quarantine(path: Path, root: Path, reason: str, manifest: list[dict]) -> None:
    target = ROOT / "training" / "quarantine" / "incompatible-images" / path.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = target.with_name(f"{target.stem}_{abs(hash(str(path))) % 10000}{target.suffix}")
    shutil.move(str(path), str(target))
    manifest.append({"original": str(path.relative_to(ROOT)), "quarantined": str(target.relative_to(ROOT)), "reason": reason})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "training" / "dataset" / "train")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest: list[dict] = []
    converted = 0
    valid = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        try:
            with Image.open(path) as image:
                image.verify()
            readable = True
        except Exception:  # noqa: BLE001 - report the file and quarantine it
            readable = False

        if suffix in ALLOWED and readable:
            valid += 1
            continue

        if readable and suffix in IMAGE_EXTENSIONS:
            # Keep a browser-safe copy under the original class folder.
            output = path.with_suffix(".jpg")
            if output.exists() and output != path:
                output = path.with_name(f"{path.stem}_converted.jpg")
            with Image.open(path) as image:
                image.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
            quarantine(path, root, f"unsupported extension {suffix}; converted to {output.name}", manifest)
            converted += 1
            valid += 1
            continue

        reason = "unreadable image" if suffix in IMAGE_EXTENSIONS else "non-image file"
        quarantine(path, root, reason, manifest)

    report = ROOT / "training" / "quarantine" / "incompatible-images-manifest.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "root": str(root.relative_to(ROOT)),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "valid_images": valid,
        "converted_images": converted,
        "quarantined": manifest,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"valid={valid} converted={converted} quarantined={len(manifest)}")
    for item in manifest:
        print(f"{item['reason']}: {item['original']}")


if __name__ == "__main__":
    main()
