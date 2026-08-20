#!/usr/bin/env python3
"""Prepare a small, traceable train-only expansion from local field feedback.

The teammate classifier did not contain several corrections collected by the
original SORT RAC app. This script copies only those user-provided photos plus
the manually reviewed, license-cleared Commons mobile-phone candidates. It
refuses exact overlap with the teammate validation and test sets.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = Path("/Users/Vy/Documents/sort rac")
OUTPUT = ROOT / "training" / "external_sources" / "local_feedback_v1"
COMMONS_PHONES = {
    "commons_mobile_phone_0e3080acac342131.jpg",
    "commons_mobile_phone_11bc0985cb0319bb.jpg",
    "commons_mobile_phone_63b2605d6a24f5bb.jpg",
    "commons_mobile_phone_b9fbb0e824a6817b.jpg",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {OUTPUT}")

    heldout_hashes = {
        digest(path)
        for split in ("val", "test")
        for path in (ROOT / "training" / "classifier_dataset" / split).glob("*/*")
        if path.is_file()
    }
    sources: list[tuple[str, Path, str, str | None]] = []
    feedback_root = (
        ORIGINAL
        / "training"
        / "dataset_curated_feedback_20260809_v1"
        / "train"
    )
    for class_name in (
        "battery",
        "paper_cup",
        "plastic_takeaway_cup",
        "plastic_water_bottle",
        "unknown",
    ):
        for path in sorted((feedback_root / class_name).glob("field_feedback_*.jpg")):
            sources.append((class_name, path, "local user field feedback", None))

    phone_root = ROOT / "training" / "candidate_dataset" / "new_items" / "mobile_phone"
    commons_records = {}
    manifest = ROOT / "training" / "source_manifests" / "new-item-candidates.jsonl"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        commons_records[Path(str(record.get("path", ""))).name] = record
    for name in sorted(COMMONS_PHONES):
        path = phone_root / name
        record = commons_records[name]
        sources.append(
            (
                "mobile_phone",
                path,
                str(record.get("sourcePage")),
                str(record.get("license")),
            )
        )

    rows = []
    seen = set()
    for class_name, source, provenance, license_name in sources:
        source_hash = digest(source)
        if source_hash in heldout_hashes:
            raise SystemExit(f"Held-out exact overlap: {source}")
        if source_hash in seen:
            continue
        seen.add(source_hash)
        destination = OUTPUT / class_name / f"local_feedback_{source_hash[:16]}.jpg"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        rows.append(
            {
                "class": class_name,
                "source": str(source),
                "destination": str(destination.relative_to(ROOT)),
                "sha256": source_hash,
                "provenance": provenance,
                "license": license_name,
                "split": "train_only",
            }
        )

    (OUTPUT / "manifest.json").write_text(
        json.dumps({"images": rows}, indent=2) + "\n", encoding="utf-8"
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["class"]] = counts.get(row["class"], 0) + 1
    print(json.dumps(counts, indent=2, sort_keys=True))
    print(f"Prepared {len(rows)} train-only images at {OUTPUT}")


if __name__ == "__main__":
    main()
