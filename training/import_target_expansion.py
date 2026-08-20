#!/usr/bin/env python3
"""Import reviewed target-expansion candidates into train only."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "training" / "classifier_dataset"
RAW_DATASET = ROOT / "training" / "dataset"
REVIEW = ROOT / "training" / "target-expansion-review.json"
OUTPUT_MANIFEST = ROOT / "training" / "source_manifests" / "target-expansion-import.jsonl"
TARGET_CLASSES = {
    "aerosol_can",
    "aluminium_drink_can",
    "paper_bag",
    "paper_cup",
    "plastic_cup_lid",
    "plastic_food_container",
    "styrofoam_container",
    "tissue",
    "plastic_takeaway_cup",
    "drink_carton",
    "snack_wrapper",
    "paperboard_packaging",
    "light_bulb",
    "hair_clip",
    "hair_tie",
    "pen_marker",
    "phone_case",
}
SOURCE_MANIFESTS = {
    "taco": ROOT / "training" / "source_manifests" / "taco-expansion-candidates.jsonl",
    "openimages": ROOT / "training" / "source_manifests" / "openimages-target-expansion-candidates.jsonl",
    "commons": ROOT / "training" / "source_manifests" / "new-item-candidates.jsonl",
}


def load_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def normalize(source: Path) -> tuple[bytes, str]:
    with Image.open(source) as source_image:
        image = ImageOps.exif_transpose(source_image).convert("RGB")
    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    temporary = source.with_suffix(".import.tmp.jpg")
    image.save(temporary, "JPEG", quality=92, optimize=True)
    payload = temporary.read_bytes()
    temporary.unlink()
    return payload, hashlib.sha256(payload).hexdigest()


def main() -> None:
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    rejected = {
        "taco": set(review["tacoRejectedPaths"]),
        "openimages": set(review["openImagesRejectedPaths"]),
    }
    commons_accepted = set(review["commonsAcceptedPaths"])
    validation_paths = set(review.get("validationPaths", []))
    test_paths = set(review.get("testPaths", []))

    for dataset_root in (CLASSIFIER, RAW_DATASET):
        for split in ("train", "val", "test"):
            for class_name in TARGET_CLASSES:
                (dataset_root / split / class_name).mkdir(parents=True, exist_ok=True)
        for split in ("train", "val", "test"):
            for class_name in TARGET_CLASSES:
                for path in (dataset_root / split / class_name).glob("expansion_*.jpg"):
                    path.unlink()

    imported: list[dict[str, object]] = []
    for source_name, manifest in SOURCE_MANIFESTS.items():
        for record in load_records(manifest):
            class_name = str(record.get("class", ""))
            source_key = str(record.get("path", ""))
            if class_name not in TARGET_CLASSES or not source_key:
                continue
            if source_name == "commons":
                if source_key not in commons_accepted:
                    continue
            elif source_key in rejected[source_name]:
                continue
            source = ROOT / source_key
            if not source.exists():
                continue
            payload, digest = normalize(source)
            split = "val" if source_key in validation_paths else "test" if source_key in test_paths else "train"
            filename = f"expansion_{source_name}_{class_name}_{digest[:16]}.jpg"
            classifier_path = CLASSIFIER / split / class_name / filename
            raw_path = RAW_DATASET / split / class_name / filename
            classifier_path.write_bytes(payload)
            shutil.copy2(classifier_path, raw_path)
            imported.append(
                {
                    **record,
                    "sourceDataset": source_name,
                    "split": split,
                    "classifierFile": classifier_path.relative_to(ROOT).as_posix(),
                    "rawDatasetFile": raw_path.relative_to(ROOT).as_posix(),
                    "importSha256": digest,
                    "review": "accepted_contact_sheet",
                }
            )

    imported.sort(key=lambda row: (str(row["class"]), str(row["classifierFile"])))
    OUTPUT_MANIFEST.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in imported),
        encoding="utf-8",
    )
    for class_name in sorted(TARGET_CLASSES):
        count = sum(record["class"] == class_name for record in imported)
        print(f"{class_name:<25} {count:>3}")
    print(f"Imported {len(imported)} reviewed images with object-disjoint splits.")


if __name__ == "__main__":
    main()
