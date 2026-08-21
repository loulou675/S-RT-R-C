"""Evaluate the best classifier checkpoint on untouched images per class."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
HAZARDOUS_CLASSES = {
    "aerosol_can",
    "battery",
    "chemical_container",
    "electronic_cable",
    "light_bulb",
    "mobile_phone",
    "power_bank",
}
CLASS_TO_BIN = {
    "aerosol_can": "hazardous",
    "aluminium_drink_can": "bottle_can",
    "battery": "hazardous",
    "cardboard_box": "paper_cardboard",
    "chemical_container": "hazardous",
    "dirty_plastic_bag": "landfill",
    "disposable_cutlery": "landfill",
    "disposable_diaper": "landfill",
    "drink_carton": "paper_cardboard",
    "electronic_cable": "hazardous",
    "food_waste": "organic",
    "fruit_peel": "organic",
    "glass_drink_bottle": "bottle_can",
    "hair_clip": "landfill",
    "hair_tie": "landfill",
    "light_bulb": "hazardous",
    "medical_mask": "landfill",
    "medicine_blister_pack": "landfill",
    "mobile_phone": "hazardous",
    "newspaper": "paper_cardboard",
    "paper_bag": "paper_cardboard",
    "paper_cup": "landfill",
    "paper_plate": "landfill",
    "paperboard_packaging": "paper_cardboard",
    "pen_marker": "landfill",
    "phone_case": "landfill",
    "plastic_bag": "clean_plastic",
    "plastic_cosmetic_container": "clean_plastic",
    "plastic_cup_lid": "clean_plastic",
    "plastic_food_container": "clean_plastic",
    "plastic_takeaway_cup": "clean_plastic",
    "plastic_water_bottle": "bottle_can",
    "power_bank": "hazardous",
    "printing_paper": "paper_cardboard",
    "sanitary_pad": "landfill",
    "snack_wrapper": "clean_plastic",
    "steel_food_can": "bottle_can",
    "styrofoam_container": "clean_plastic",
    "tissue": "landfill",
    "unknown": "unknown",
    "vegetable_scraps": "organic",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=Path,
        default=(
            ROOT
            / "training"
            / "checkpoints"
            / "candidate_v23_full40_seed_frozen_sparse_search.pt"
        ),
    )
    parser.add_argument("--data", type=Path, default=ROOT / "training" / "classifier_dataset" / "test")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    samples: list[tuple[Path, str]] = []
    for class_dir in sorted(path for path in args.data.iterdir() if path.is_dir()):
        samples.extend(
            (path, class_dir.name)
            for path in sorted(class_dir.iterdir())
            if path.suffix.lower() in IMAGE_SUFFIXES
        )
    if not samples:
        raise SystemExit(f"No test images found under {args.data}")

    model = YOLO(str(args.model), task="classify")
    options = {
        "imgsz": 224,
        "verbose": False,
        "stream": False,
    }
    if args.device:
        options["device"] = args.device
    if args.model.suffix.lower() == ".onnx":
        # The browser export uses a fixed batch size of one.
        results = [
            model.predict(source=str(path), **options)[0]
            for path, _ in samples
        ]
    else:
        results = model.predict(source=[str(path) for path, _ in samples], **options)

    per_class: dict[str, Counter[str]] = defaultdict(Counter)
    confidences: dict[str, list[float]] = defaultdict(list)
    errors: Counter[tuple[str, str]] = Counter()
    total_correct = 0
    bin_total_correct = 0
    bin_confusion: dict[str, Counter[str]] = defaultdict(Counter)
    grouped_bin_total_correct = 0
    grouped_bin_confusion: dict[str, Counter[str]] = defaultdict(Counter)
    sample_predictions: list[dict[str, object]] = []

    for (path, expected), result in zip(samples, results, strict=True):
        predicted = model.names[int(result.probs.top1)]
        confidence = float(result.probs.top1conf)
        top5_indices = [int(index) for index in result.probs.top5]
        top5_confidences = [float(value) for value in result.probs.top5conf]
        sample_predictions.append(
            {
                "path": str(path),
                "expected": expected,
                "predicted": predicted,
                "correct": predicted == expected,
                "confidence": round(confidence, 6),
                "top5": [
                    {
                        "class": model.names[index],
                        "confidence": round(top5_confidence, 6),
                    }
                    for index, top5_confidence in zip(
                        top5_indices, top5_confidences, strict=True
                    )
                ],
            }
        )
        per_class[expected][predicted] += 1
        confidences[expected].append(confidence)
        if predicted == expected:
            total_correct += 1
        else:
            errors[(expected, predicted)] += 1

        expected_bin = CLASS_TO_BIN[expected]
        predicted_bin = CLASS_TO_BIN[predicted]
        bin_confusion[expected_bin][predicted_bin] += 1
        if predicted_bin == expected_bin:
            bin_total_correct += 1

        grouped_scores: Counter[str] = Counter()
        probabilities = result.probs.data.tolist()
        for class_index, probability in enumerate(probabilities):
            grouped_scores[CLASS_TO_BIN[model.names[class_index]]] += float(probability)
        grouped_predicted_bin = grouped_scores.most_common(1)[0][0]
        grouped_bin_confusion[expected_bin][grouped_predicted_bin] += 1
        if grouped_predicted_bin == expected_bin:
            grouped_bin_total_correct += 1

    class_rows = []
    for class_name in sorted(per_class):
        total = sum(per_class[class_name].values())
        correct = per_class[class_name][class_name]
        class_rows.append(
            {
                "class": class_name,
                "correct": correct,
                "total": total,
                "recall": round(correct / total, 4),
                "mean_top1_confidence": round(sum(confidences[class_name]) / total, 4),
                "hazardous": class_name in HAZARDOUS_CLASSES,
                "predictions": dict(per_class[class_name].most_common()),
            }
        )

    macro_recall = sum(row["recall"] for row in class_rows) / len(class_rows)
    hazardous_rows = [row for row in class_rows if row["hazardous"]]
    bin_rows = []
    for bin_name in sorted(bin_confusion):
        total = sum(bin_confusion[bin_name].values())
        correct = bin_confusion[bin_name][bin_name]
        bin_rows.append(
            {
                "bin": bin_name,
                "correct": correct,
                "total": total,
                "recall": round(correct / total, 4),
                "predictions": dict(bin_confusion[bin_name].most_common()),
            }
        )
    known_bin_rows = [row for row in bin_rows if row["bin"] != "unknown"]
    known_images = sum(row["total"] for row in known_bin_rows)
    known_correct = sum(row["correct"] for row in known_bin_rows)
    hazardous_macro_recall = (
        round(sum(row["recall"] for row in hazardous_rows) / len(hazardous_rows), 4)
        if hazardous_rows
        else None
    )
    known_item_bin_accuracy = (
        round(known_correct / known_images, 4) if known_images else None
    )
    known_bin_macro_recall = (
        round(sum(row["recall"] for row in known_bin_rows) / len(known_bin_rows), 4)
        if known_bin_rows
        else None
    )
    grouped_bin_rows = []
    for bin_name in sorted(grouped_bin_confusion):
        total = sum(grouped_bin_confusion[bin_name].values())
        correct = grouped_bin_confusion[bin_name][bin_name]
        grouped_bin_rows.append(
            {
                "bin": bin_name,
                "correct": correct,
                "total": total,
                "recall": round(correct / total, 4),
                "predictions": dict(grouped_bin_confusion[bin_name].most_common()),
            }
        )
    grouped_known_rows = [row for row in grouped_bin_rows if row["bin"] != "unknown"]
    grouped_known_images = sum(row["total"] for row in grouped_known_rows)
    grouped_known_correct = sum(row["correct"] for row in grouped_known_rows)
    report = {
        "model": str(args.model),
        "test_data": str(args.data),
        "images": len(samples),
        "classes": len(class_rows),
        "top1_accuracy": round(total_correct / len(samples), 4),
        "macro_recall": round(macro_recall, 4),
        "hazardous_macro_recall": hazardous_macro_recall,
        "bin_accuracy_including_unknown": round(bin_total_correct / len(samples), 4),
        "known_item_bin_accuracy": known_item_bin_accuracy,
        "known_bin_macro_recall": known_bin_macro_recall,
        "grouped_bin_accuracy_including_unknown": round(grouped_bin_total_correct / len(samples), 4),
        "grouped_known_item_bin_accuracy": round(grouped_known_correct / grouped_known_images, 4),
        "per_bin": bin_rows,
        "grouped_per_bin": grouped_bin_rows,
        "per_class": class_rows,
        "sample_predictions": sample_predictions,
        "top_confusions": [
            {"expected": expected, "predicted": predicted, "count": count}
            for (expected, predicted), count in errors.most_common(20)
        ],
    }

    output = args.output or args.model.parents[1] / "per-class-evaluation.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Top-1 accuracy: {report['top1_accuracy']:.1%}")
    print(f"Macro recall: {report['macro_recall']:.1%}")
    hazardous_display = (
        f"{hazardous_macro_recall:.1%}" if hazardous_macro_recall is not None else "n/a"
    )
    known_accuracy_display = (
        f"{known_item_bin_accuracy:.1%}"
        if known_item_bin_accuracy is not None
        else "n/a"
    )
    known_macro_display = (
        f"{known_bin_macro_recall:.1%}"
        if known_bin_macro_recall is not None
        else "n/a"
    )
    print(f"Hazardous macro recall: {hazardous_display}")
    print(f"Known-item bin accuracy: {known_accuracy_display}")
    print(f"Known-bin macro recall: {known_macro_display}")
    print(f"Grouped known-item bin accuracy: {report['grouped_known_item_bin_accuracy']:.1%}")
    print("\nPer bin:")
    for row in sorted(bin_rows, key=lambda item: item["bin"]):
        print(f"  {row['bin']:<20} {row['correct']:>3}/{row['total']:<3} {row['recall']:>6.1%}")
    print("\nPer class:")
    for row in sorted(class_rows, key=lambda item: (item["recall"], item["class"])):
        print(f"  {row['class']:<29} {row['correct']:>2}/{row['total']:<2} {row['recall']:>6.1%}")
    print(f"\nSaved {output}")


if __name__ == "__main__":
    main()
