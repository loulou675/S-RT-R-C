"""Verify that a teammate has the complete local AI training handoff."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def image_count(folder: Path) -> int:
    return sum(
        1
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def require_file(path: Path, failures: list[str], minimum_bytes: int = 1) -> None:
    if not path.is_file():
        failures.append(f"Missing file: {path.relative_to(ROOT)}")
    elif path.stat().st_size < minimum_bytes:
        failures.append(f"File is unexpectedly small: {path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--with-components",
        action="store_true",
        help="Also require the component detector dataset and checkpoint.",
    )
    args = parser.parse_args()

    failures: list[str] = []
    warnings: list[str] = []
    classes_path = ROOT / "training" / "classes.json"
    require_file(classes_path, failures)
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)

    configured = json.loads(classes_path.read_text(encoding="utf-8"))["classes"]
    if len(configured) != 36:
        failures.append(f"Expected 36 classifier classes, found {len(configured)}.")

    dataset = ROOT / "training" / "classifier_dataset"
    total_images = 0
    print("Classifier dataset")
    print("-" * 72)
    for split in ("train", "val", "test"):
        split_dir = dataset / split
        folders = sorted(path.name for path in split_dir.iterdir() if path.is_dir()) if split_dir.is_dir() else []
        missing = sorted(set(configured) - set(folders))
        extra = sorted(set(folders) - set(configured))
        if missing:
            failures.append(f"{split}: missing class folders: {', '.join(missing)}")
        if extra:
            failures.append(f"{split}: unexpected class folders: {', '.join(extra)}")

        split_total = 0
        empty_classes: list[str] = []
        for class_name in configured:
            count = image_count(split_dir / class_name)
            split_total += count
            if count == 0:
                empty_classes.append(class_name)
        total_images += split_total
        print(f"{split:>5}: {split_total:5} images across {len(folders):2} folders")
        if empty_classes:
            warnings.append(f"{split}: empty classes: {', '.join(empty_classes)}")

    if total_images == 0:
        failures.append("Classifier dataset contains no images.")

    require_file(ROOT / "training" / "checkpoints" / "waste_classifier.pt", failures, 1_000_000)
    require_file(ROOT / "training" / "checkpoints" / "waste_classifier_36_seed.pt", failures, 1_000_000)
    require_file(ROOT / "public" / "models" / "waste_classifier.onnx", failures, 1_000_000)

    labels_path = ROOT / "public" / "models" / "labels.json"
    require_file(labels_path, failures)
    if labels_path.is_file():
        model_codes = [entry["code"] for entry in json.loads(labels_path.read_text(encoding="utf-8"))["labels"]]
        if model_codes != sorted(configured):
            failures.append("public/models/labels.json does not match the 36-class dataset order.")

    if args.with_components:
        component_dataset = ROOT / "training" / "component_dataset"
        require_file(component_dataset / "data.yaml", failures)
        component_counts = {
            split: image_count(component_dataset / "images" / split)
            for split in ("train", "val", "test")
        }
        print("\nComponent dataset")
        print("-" * 72)
        for split, count in component_counts.items():
            print(f"{split:>5}: {count:5} images")
            if count == 0:
                failures.append(f"Component dataset {split} split is empty.")
        require_file(ROOT / "training" / "checkpoints" / "component_detector.pt", failures, 1_000_000)
        require_file(ROOT / "public" / "models" / "waste_components.onnx", failures, 1_000_000)
        require_file(ROOT / "public" / "models" / "component_labels.json", failures)

    if warnings:
        print("\nWarnings")
        print("-" * 72)
        for warning in warnings:
            print(f"- {warning}")

    if failures:
        print("\nSetup is incomplete")
        print("-" * 72)
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("\nPASS: the teammate AI setup is complete and ready to evaluate or train.")


if __name__ == "__main__":
    main()
