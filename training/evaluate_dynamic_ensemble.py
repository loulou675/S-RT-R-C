#!/usr/bin/env python3
"""Evaluate a calibrated ensemble with the deployed browser preprocessing."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import torch
from ultralytics import YOLO

from calibrate_dynamic_ensemble import calibrated_logits, feature_stack
from calibrate_four_model_ensemble import infer_any
from evaluate_per_class import CLASS_TO_BIN, HAZARDOUS_CLASSES
from evaluate_two_model_ensemble import samples_for_split


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, nargs="+", required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("val", "test"), default="test")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=48)
    args = parser.parse_args()

    saved = json.loads(args.calibration.read_text(encoding="utf-8"))
    temperatures = torch.tensor(saved["temperatures"], dtype=torch.float32)
    if len(args.models) != len(temperatures):
        raise SystemExit("Model count does not match calibration")
    probe = YOLO(str(args.models[0]), task="classify")
    names = [probe.names[index] for index in range(len(probe.names))]
    del probe
    samples = samples_for_split(
        args.data.resolve(), args.split, {name: index for index, name in enumerate(names)}
    )
    all_logits: list[torch.Tensor] = []
    labels: torch.Tensor | None = None
    for path in args.models:
        model_names, logits, current_labels = infer_any(path, samples, args.device, args.batch, names)
        if model_names != names:
            raise SystemExit(f"Model class order does not align: {path}")
        if labels is not None and not torch.equal(labels, current_labels):
            raise SystemExit("Sample labels do not align")
        labels = current_labels
        all_logits.append(logits)
    if labels is None:
        raise SystemExit("No test labels were loaded")

    theta = torch.tensor(saved["theta"], dtype=torch.float32)
    bias = torch.tensor(saved["bias"], dtype=torch.float32)
    probabilities = calibrated_logits(feature_stack(all_logits, temperatures), theta, bias).softmax(1)
    predictions = probabilities.argmax(1)
    class_confusion: dict[str, Counter[str]] = defaultdict(Counter)
    direct_bins: dict[str, Counter[str]] = defaultdict(Counter)
    grouped_bins: dict[str, Counter[str]] = defaultdict(Counter)
    for label, prediction, row in zip(labels.tolist(), predictions.tolist(), probabilities, strict=True):
        expected = names[label]
        predicted = names[prediction]
        class_confusion[expected][predicted] += 1
        expected_bin = CLASS_TO_BIN[expected]
        direct_bins[expected_bin][CLASS_TO_BIN[predicted]] += 1
        grouped = Counter()
        for index, probability in enumerate(row.tolist()):
            grouped[CLASS_TO_BIN[names[index]]] += probability
        grouped_bins[expected_bin][grouped.most_common(1)[0][0]] += 1

    per_class = []
    for name in names:
        total = sum(class_confusion[name].values())
        correct = class_confusion[name][name]
        per_class.append(
            {
                "class": name,
                "correct": correct,
                "total": total,
                "recall": correct / total if total else 0.0,
                "hazardous": name in HAZARDOUS_CLASSES,
                "predictions": dict(class_confusion[name].most_common()),
            }
        )

    def summarize_bins(confusion: dict[str, Counter[str]]) -> list[dict]:
        rows = []
        for name in sorted(confusion):
            total = sum(confusion[name].values())
            correct = confusion[name][name]
            rows.append(
                {
                    "bin": name,
                    "correct": correct,
                    "total": total,
                    "recall": correct / total,
                    "predictions": dict(confusion[name].most_common()),
                }
            )
        return rows

    direct_rows = summarize_bins(direct_bins)
    grouped_rows = summarize_bins(grouped_bins)
    known_direct = [row for row in direct_rows if row["bin"] != "unknown"]
    known_grouped = [row for row in grouped_rows if row["bin"] != "unknown"]
    hazardous = [row for row in per_class if row["hazardous"]]
    unknown = next(row for row in per_class if row["class"] == "unknown")

    report = {
        "models": [str(path) for path in args.models],
        "calibration": str(args.calibration),
        "images": len(labels),
        "split": args.split,
        "top1_accuracy": sum(row["correct"] for row in per_class) / len(labels),
        "top1_correct": sum(row["correct"] for row in per_class),
        "macro_recall": sum(row["recall"] for row in per_class) / len(per_class),
        "hazardous_macro_recall": sum(row["recall"] for row in hazardous) / len(hazardous),
        "known_item_bin_accuracy": sum(row["correct"] for row in known_direct)
        / sum(row["total"] for row in known_direct),
        "grouped_known_item_bin_accuracy": sum(row["correct"] for row in known_grouped)
        / sum(row["total"] for row in known_grouped),
        "unknown_rejection_recall": unknown["recall"],
        "per_bin": direct_rows,
        "grouped_per_bin": grouped_rows,
        "per_class": per_class,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"top1={report['top1_accuracy']:.4%} ({report['top1_correct']}/{len(labels)})")
    print(f"macro_recall={report['macro_recall']:.4%}")
    print(f"hazardous_macro_recall={report['hazardous_macro_recall']:.4%}")
    print(f"known_item_bin_accuracy={report['known_item_bin_accuracy']:.4%}")
    print(f"grouped_known_item_bin_accuracy={report['grouped_known_item_bin_accuracy']:.4%}")
    print(f"unknown_rejection_recall={report['unknown_rejection_recall']:.4%}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
