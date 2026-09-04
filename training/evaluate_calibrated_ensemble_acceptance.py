#!/usr/bin/env python3
"""Produce acceptance metrics for the locked four-model calibrated ensemble."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import torch
from ultralytics import YOLO

from calibrate_four_model_ensemble import calibrated_logits, feature_stack
from evaluate_per_class import CLASS_TO_BIN, HAZARDOUS_CLASSES
from evaluate_two_model_ensemble import infer, samples_for_split


def main() -> None:
    parser = argparse.ArgumentParser()
    for letter in "abcd":
        parser.add_argument(f"--model-{letter}", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=48)
    args = parser.parse_args()

    paths = [args.model_a, args.model_b, args.model_c, args.model_d]
    probe = YOLO(str(paths[0]), task="classify")
    names = [probe.names[index] for index in range(len(probe.names))]
    del probe
    class_index = {name: index for index, name in enumerate(names)}
    samples = samples_for_split(args.data.resolve(), "test", class_index)
    all_logits = []
    labels = None
    for path in paths:
        model_names, logits, current_labels = infer(path, samples, args.device, args.batch)
        if model_names != names:
            raise SystemExit("Model class orders do not align")
        if labels is not None and not torch.equal(labels, current_labels):
            raise SystemExit("Sample labels do not align")
        labels = current_labels
        all_logits.append(logits)

    saved = json.loads(args.calibration.read_text(encoding="utf-8"))
    theta = torch.tensor(saved["theta"], dtype=torch.float32)
    bias = torch.tensor(saved["bias"], dtype=torch.float32)
    probabilities = calibrated_logits(feature_stack(all_logits), theta, bias).softmax(1)
    predictions = probabilities.argmax(1)

    class_confusion = defaultdict(Counter)
    bin_confusion = defaultdict(Counter)
    grouped_bin_confusion = defaultdict(Counter)
    for label, prediction, row in zip(labels.tolist(), predictions.tolist(), probabilities, strict=True):
        expected = names[label]
        predicted = names[prediction]
        class_confusion[expected][predicted] += 1
        expected_bin = CLASS_TO_BIN[expected]
        bin_confusion[expected_bin][CLASS_TO_BIN[predicted]] += 1
        grouped = Counter()
        for index, probability in enumerate(row.tolist()):
            grouped[CLASS_TO_BIN[names[index]]] += probability
        grouped_bin_confusion[expected_bin][grouped.most_common(1)[0][0]] += 1

    per_class = []
    for class_name in names:
        total = sum(class_confusion[class_name].values())
        correct = class_confusion[class_name][class_name]
        per_class.append({
            "class": class_name,
            "correct": correct,
            "total": total,
            "recall": correct / total if total else 0.0,
            "hazardous": class_name in HAZARDOUS_CLASSES,
            "predictions": dict(class_confusion[class_name].most_common()),
        })

    total_correct = sum(row["correct"] for row in per_class)
    macro_recall = sum(row["recall"] for row in per_class) / len(per_class)
    hazardous = [row for row in per_class if row["hazardous"]]
    hazardous_macro = sum(row["recall"] for row in hazardous) / len(hazardous)

    def bin_rows(confusion):
        rows = []
        for bin_name in sorted(confusion):
            total = sum(confusion[bin_name].values())
            correct = confusion[bin_name][bin_name]
            rows.append({
                "bin": bin_name,
                "correct": correct,
                "total": total,
                "recall": correct / total,
                "predictions": dict(confusion[bin_name].most_common()),
            })
        return rows

    direct_bins = bin_rows(bin_confusion)
    grouped_bins = bin_rows(grouped_bin_confusion)
    direct_known = [row for row in direct_bins if row["bin"] != "unknown"]
    grouped_known = [row for row in grouped_bins if row["bin"] != "unknown"]
    direct_known_accuracy = sum(row["correct"] for row in direct_known) / sum(row["total"] for row in direct_known)
    grouped_known_accuracy = sum(row["correct"] for row in grouped_known) / sum(row["total"] for row in grouped_known)
    unknown_row = next(row for row in per_class if row["class"] == "unknown")

    report = {
        "candidate": "v61 four-model class-wise calibrated ensemble",
        "calibration": str(args.calibration),
        "models": [str(path) for path in paths],
        "test_data": str(args.data),
        "images": len(labels),
        "top1_accuracy": total_correct / len(labels),
        "top1_correct": total_correct,
        "macro_recall": macro_recall,
        "hazardous_macro_recall": hazardous_macro,
        "known_item_bin_accuracy": direct_known_accuracy,
        "grouped_known_item_bin_accuracy": grouped_known_accuracy,
        "unknown_rejection_recall": unknown_row["recall"],
        "per_bin": direct_bins,
        "grouped_per_bin": grouped_bins,
        "per_class": per_class,
    }

    if args.baseline_report:
        baseline = json.loads(args.baseline_report.read_text(encoding="utf-8"))
        baseline_classes = {row["class"]: row for row in baseline["per_class"]}
        report["baseline_comparison"] = {
            "baseline": str(args.baseline_report),
            "top1_delta": report["top1_accuracy"] - baseline["top1_accuracy"],
            "macro_recall_delta": report["macro_recall"] - baseline["macro_recall"],
            "hazardous_macro_recall_delta": report["hazardous_macro_recall"] - baseline["hazardous_macro_recall"],
            "known_item_bin_accuracy_delta": report["known_item_bin_accuracy"] - baseline["known_item_bin_accuracy"],
            "grouped_known_item_bin_accuracy_delta": report["grouped_known_item_bin_accuracy"] - baseline["grouped_known_item_bin_accuracy"],
            "per_class_recall_delta": {
                row["class"]: row["recall"] - baseline_classes[row["class"]]["recall"]
                for row in per_class
            },
        }

    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"top1={report['top1_accuracy']:.4%} ({total_correct}/{len(labels)})")
    print(f"macro_recall={report['macro_recall']:.4%}")
    print(f"hazardous_macro_recall={report['hazardous_macro_recall']:.4%}")
    print(f"known_item_bin_accuracy={report['known_item_bin_accuracy']:.4%}")
    print(f"grouped_known_item_bin_accuracy={report['grouped_known_item_bin_accuracy']:.4%}")
    print(f"unknown_rejection_recall={report['unknown_rejection_recall']:.4%}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
