"""Import license-cleared internet candidates into training only.

Validation and test remain independent real/phone imagery; web images must not
inflate evaluation metrics for either existing weak classes or new classes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "training" / "candidate_dataset" / "new_items"
DATASET = ROOT / "training" / "classifier_dataset"
MANIFEST = ROOT / "training" / "source_manifests" / "new-item-training-import.jsonl"
ACTIVE_CLASSES = {
    "aerosol_can",
    "disposable_cutlery",
    "disposable_diaper",
    "drink_carton",
    "hair_clip",
    "hair_tie",
    "medical_mask",
    "light_bulb",
    "paperboard_packaging",
    "pen_marker",
    "phone_case",
    "plastic_food_container",
    "plastic_takeaway_cup",
    "sanitary_pad",
    "snack_wrapper",
    "styrofoam_container",
    "tissue",
}
COLLECTOR_MANIFEST = ROOT / "training" / "source_manifests" / "new-item-candidates.jsonl"


def approved_license(record: dict[str, object]) -> bool:
    license_name = str(record.get("license") or "").strip().casefold()
    return license_name not in {"", "unknown_review_needed", "per_file_review_required"}


def main() -> None:
    for split in ("train", "val", "test"):
        for path in (DATASET / split).glob("*/internet_new_*.jpg"):
            path.unlink()

    source_records: dict[str, dict[str, object]] = {}
    if COLLECTOR_MANIFEST.exists():
        for line in COLLECTOR_MANIFEST.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            source_records[str(record.get("path", ""))] = record

    records: list[dict[str, object]] = []
    for class_name in sorted(ACTIVE_CLASSES):
        for split in ("train", "val", "test"):
            (DATASET / split / class_name).mkdir(parents=True, exist_ok=True)
        paths = sorted((SOURCE / class_name).glob("*.jpg"))
        for path in paths:
            source_key = path.relative_to(ROOT).as_posix()
            source_record = source_records.get(source_key, {})
            if not approved_license(source_record):
                continue
            with Image.open(path) as source_image:
                image = ImageOps.exif_transpose(source_image).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            payload_path = path.with_suffix(".normalized.tmp.jpg")
            image.save(payload_path, "JPEG", quality=90, optimize=True)
            payload = payload_path.read_bytes()
            payload_path.unlink()
            digest = hashlib.sha256(payload).hexdigest()
            split = "train"
            destination = DATASET / split / class_name / f"internet_new_{class_name}_{digest[:16]}.jpg"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            records.append(
                {
                    "source": source_key,
                    "destination": str(destination.relative_to(ROOT)),
                    "class": class_name,
                    "split": split,
                    "sha256": digest,
                    "sourcePage": source_record.get("sourcePage"),
                    "sourceFile": source_record.get("sourceFile"),
                    "license": source_record.get("license"),
                    "creator": source_record.get("creator"),
                }
            )

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    counts: dict[tuple[str, str], int] = {}
    for record in records:
        key = (record["class"], record["split"])
        counts[key] = counts.get(key, 0) + 1
    for (class_name, split), count in sorted(counts.items()):
        print(f"{class_name:<16} {split:<5} {count:>3}")
    print(f"Imported {len(records)} reviewed internet candidates.")


if __name__ == "__main__":
    main()
