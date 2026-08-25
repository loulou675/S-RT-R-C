#!/usr/bin/env python3
"""Select a conservative low-confidence specialist gate on validation data."""

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


def ensemble_probabilities(models, calibration, samples, names, device, batch):
    saved = json.loads(calibration.read_text(encoding="utf-8"))
    temperatures = torch.tensor(saved["temperatures"], dtype=torch.float32)
    logits = []
    labels = None
    for path in models:
        model_names, values, current_labels = infer_any(path, samples, device, batch, names)
        if model_names != names:
            raise SystemExit(f"Model class order does not align: {path}")
        if labels is not None and not torch.equal(labels, current_labels):
            raise SystemExit("Sample labels do not align")
        logits.append(values)
        labels = current_labels
    if labels is None:
        raise SystemExit("No samples loaded")
    theta = torch.tensor(saved["theta"], dtype=torch.float32)
    bias = torch.tensor(saved["bias"], dtype=torch.float32)
    return calibrated_logits(feature_stack(logits, temperatures), theta, bias).softmax(1), labels


def metrics(probabilities, labels, names):
    predictions = probabilities.argmax(1)
    exact = float((predictions == labels).float().mean())
    class_rows = defaultdict(Counter)
    direct = defaultdict(Counter)
    grouped = defaultdict(Counter)
    for label, prediction, row in zip(labels.tolist(), predictions.tolist(), probabilities, strict=True):
        expected = names[label]
        predicted = names[prediction]
        class_rows[expected][predicted] += 1
        expected_bin = CLASS_TO_BIN[expected]
        direct[expected_bin][CLASS_TO_BIN[predicted]] += 1
        bin_scores = Counter()
        for index, score in enumerate(row.tolist()):
            bin_scores[CLASS_TO_BIN[names[index]]] += score
        grouped[expected_bin][bin_scores.most_common(1)[0][0]] += 1

    def recall(name):
        total = sum(class_rows[name].values())
        return class_rows[name][name] / total if total else 0.0

    hazardous = sum(recall(name) for name in HAZARDOUS_CLASSES) / len(HAZARDOUS_CLASSES)
    unknown = recall("unknown")
    known_direct = sum(rows[name] for name, rows in direct.items() if name != "unknown")
    known_total = sum(sum(rows.values()) for name, rows in direct.items() if name != "unknown")
    grouped_correct = sum(rows[name] for name, rows in grouped.items() if name != "unknown")
    grouped_total = sum(sum(rows.values()) for name, rows in grouped.items() if name != "unknown")
    return {
        "top1": exact,
        "hazardous_macro_recall": hazardous,
        "unknown_recall": unknown,
        "known_bin_accuracy": known_direct / known_total,
        "grouped_known_bin_accuracy": grouped_correct / grouped_total,
    }


def apply_gate(active, specialist, names, focus, confidence, margin):
    active_confidence, active_prediction = active.max(1)
    specialist_confidence, specialist_prediction = specialist.max(1)
    focus_indices = torch.tensor([names.index(name) for name in focus], dtype=torch.long)
    focused = (specialist_prediction[:, None] == focus_indices[None, :]).any(1)
    use_specialist = (
        focused
        & (active_confidence < confidence)
        & (specialist_confidence >= active_confidence + margin)
    )
    result = active.clone()
    result[use_specialist] = specialist[use_specialist]
    return result, use_specialist


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--active-models", type=Path, nargs="+", required=True)
    parser.add_argument("--active-calibration", type=Path, required=True)
    parser.add_argument("--specialist-models", type=Path, nargs="+", required=True)
    parser.add_argument("--specialist-calibration", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--focus", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=48)
    args = parser.parse_args()

    probe = YOLO(str(args.active_models[0]), task="classify")
    names = [probe.names[index] for index in range(len(probe.names))]
    del probe
    unknown = sorted(set(args.focus) - set(names))
    if unknown:
        raise SystemExit(f"Unknown focus classes: {unknown}")
    class_index = {name: index for index, name in enumerate(names)}

    split_values = {}
    for split in ("val", "test"):
        samples = samples_for_split(args.data.resolve(), split, class_index)
        active, labels = ensemble_probabilities(
            args.active_models, args.active_calibration, samples, names, args.device, args.batch
        )
        specialist, specialist_labels = ensemble_probabilities(
            args.specialist_models,
            args.specialist_calibration,
            samples,
            names,
            args.device,
            args.batch,
        )
        if not torch.equal(labels, specialist_labels):
            raise SystemExit("Active and specialist labels do not align")
        split_values[split] = (active, specialist, labels)

    active_val, specialist_val, val_labels = split_values["val"]
    baseline = metrics(active_val, val_labels, names)
    candidates = []
    for confidence in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70):
        for margin in (-0.05, 0.0, 0.03, 0.05, 0.08, 0.10):
            probabilities, mask = apply_gate(
                active_val, specialist_val, names, args.focus, confidence, margin
            )
            row = {
                "confidence": confidence,
                "margin": margin,
                "fallback_count": int(mask.sum()),
                "fallback_rate": float(mask.float().mean()),
                **metrics(probabilities, val_labels, names),
            }
            if (
                row["hazardous_macro_recall"] >= baseline["hazardous_macro_recall"]
                and row["unknown_recall"] >= baseline["unknown_recall"]
                and row["grouped_known_bin_accuracy"] >= baseline["grouped_known_bin_accuracy"]
            ):
                candidates.append(row)
    candidates.sort(
        key=lambda row: (
            -row["top1"],
            -row["known_bin_accuracy"],
            row["fallback_rate"],
        )
    )
    selected = candidates[0] if candidates else None
    report = {"focus": args.focus, "validation_baseline": baseline, "selected": selected}
    if selected:
        active_test, specialist_test, test_labels = split_values["test"]
        probabilities, mask = apply_gate(
            active_test,
            specialist_test,
            names,
            args.focus,
            selected["confidence"],
            selected["margin"],
        )
        report["test_baseline"] = metrics(active_test, test_labels, names)
        report["test_selected"] = {
            "fallback_count": int(mask.sum()),
            "fallback_rate": float(mask.float().mean()),
            **metrics(probabilities, test_labels, names),
        }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
