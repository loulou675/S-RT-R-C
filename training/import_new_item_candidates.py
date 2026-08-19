"""Import reviewed internet candidates for the four active new item classes."""

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
    "disposable_diaper",
    "drink_carton",
    "hair_clip",
    "hair_tie",
    "medical_mask",
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
NEW_WEAK_CLASSES = ACTIVE_CLASSES - {"hair_clip", "hair_tie", "pen_marker", "phone_case"}


def split_for(class_name: str, digest: str, index: int, count: int) -> str:
    if class_name in NEW_WEAK_CLASSES:
        # Internet additions improve training diversity but never redefine the
        # independent phone/TACO validation and test sets.
        return "train"
    if class_name == "phone_case":
        # The real-image folder already supplies one physical case for train.
        return "test"
    if count <= 3:
        return ("train", "val", "test")[index % 3]
    bucket = int(digest[:8], 16) % 100
    return "train" if bucket < 70 else "val" if bucket < 85 else "test"


def main() -> None:
    for split in ("train", "val", "test"):
        for path in (DATASET / split).glob("*/internet_new_*.jpg"):
            path.unlink()

    records: list[dict[str, str]] = []
    for class_name in sorted(ACTIVE_CLASSES):
        paths = sorted((SOURCE / class_name).glob("*.jpg"))
        for index, path in enumerate(paths):
            with Image.open(path) as source_image:
                image = ImageOps.exif_transpose(source_image).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            payload_path = path.with_suffix(".normalized.tmp.jpg")
            image.save(payload_path, "JPEG", quality=90, optimize=True)
            payload = payload_path.read_bytes()
            payload_path.unlink()
            digest = hashlib.sha256(payload).hexdigest()
            split = split_for(class_name, digest, index, len(paths))
            destination = DATASET / split / class_name / f"internet_new_{class_name}_{digest[:16]}.jpg"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            records.append(
                {
                    "source": str(path.relative_to(ROOT)),
                    "destination": str(destination.relative_to(ROOT)),
                    "class": class_name,
                    "split": split,
                    "sha256": digest,
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
