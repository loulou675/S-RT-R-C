#!/usr/bin/env python3
"""Download manually selected web-image candidates for sparse classes."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "training" / "curated-weak-class-web-seeds.json"
CANDIDATE_ROOT = ROOT / "training" / "candidate_dataset" / "new_items"
MANIFEST = ROOT / "training" / "source_manifests" / "new-item-candidates.jsonl"
USER_AGENT = "Mozilla/5.0 SORT-RAC educational dataset review"


def load_manifest() -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    if MANIFEST.exists():
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            records[str(record.get("sha256", ""))] = record
    return records


def main() -> None:
    records = load_manifest()
    added = 0
    failed = 0
    for seed in json.loads(SEEDS.read_text(encoding="utf-8")):
        try:
            response = requests.get(seed["url"], headers={"User-Agent": USER_AGENT}, timeout=45)
            response.raise_for_status()
            image = ImageOps.exif_transpose(Image.open(BytesIO(response.content))).convert("RGB")
            if min(image.size) < 200:
                raise ValueError("image is too small")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, "JPEG", quality=90, optimize=True)
            payload = output.getvalue()
        except Exception as error:
            failed += 1
            print(f"FAILED {seed['class']}: {seed['url']} ({error})")
            continue
        digest = hashlib.sha256(payload).hexdigest()
        if digest in records:
            continue
        destination = CANDIDATE_ROOT / seed["class"] / f"web_{seed['class']}_{digest[:16]}.jpg"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        records[digest] = {
            "class": seed["class"],
            "bin": "landfill",
            "path": destination.relative_to(ROOT).as_posix(),
            "sha256": digest,
            "source": "curated web image search",
            "sourcePage": seed["sourcePage"],
            "sourceImage": seed["url"],
            "sourceFile": seed["title"],
            "license": "manual_review_required",
            "width": image.width,
            "height": image.height,
            "review": "candidate_only",
        }
        added += 1
    ordered = sorted(records.values(), key=lambda row: (str(row.get("class")), str(row.get("path"))))
    MANIFEST.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered), encoding="utf-8")
    print(f"Added {added}; failed {failed}; manifest total {len(ordered)}")


if __name__ == "__main__":
    main()
