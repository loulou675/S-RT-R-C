#!/usr/bin/env python3
"""Evaluate classifier-row interpolation levels in a locked calibrated ensemble."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import torch
from ultralytics import YOLO

from calibrate_four_model_ensemble import calibrated_logits, feature_stack
from evaluate_per_class import CLASS_TO_BIN, HAZARDOUS_CLASSES
from evaluate_two_model_ensemble import infer, samples_for_split


def metrics(probabilities: torch.Tensor, labels: torch.Tensor, names: list[str]) -> dict:
    predictions = probabilities.argmax(1)
    correct = int((predictions == labels).sum())
    class_correct = Counter()
    class_total = Counter()
    direct_known_correct = 0
    grouped_known_correct = 0
    known_total = 0
    for label, prediction, row in zip(labels.tolist(), predictions.tolist(), probabilities, strict=True):
        expected = names[label]
        predicted = names[prediction]
        class_total[expected] += 1
        class_correct[expected] += predicted == expected
        if expected != "unknown":
            known_total += 1
            direct_known_correct += CLASS_TO_BIN[predicted] == CLASS_TO_BIN[expected]
            grouped = Counter()
            for index, probability in enumerate(row.tolist()):
                grouped[CLASS_TO_BIN[names[index]]] += probability
            grouped_known_correct += grouped.most_common(1)[0][0] == CLASS_TO_BIN[expected]
    recalls = {
        name: class_correct[name] / class_total[name] if class_total[name] else 0.0
        for name in names
    }
    hazardous = [recalls[name] for name in HAZARDOUS_CLASSES]
    return {
        "top1Correct": correct,
        "top1": correct / len(labels),
        "macroRecall": sum(recalls.values()) / len(recalls),
        "hazardousMacroRecall": sum(hazardous) / len(hazardous),
        "knownItemBinAccuracy": direct_known_correct / known_total,
        "groupedKnownItemBinAccuracy": grouped_known_correct / known_total,
        "unknownRejectionRecall": recalls["unknown"],
        "plasticWaterBottleRecall": recalls["plastic_water_bottle"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--model-b", type=Path, required=True)
    parser.add_argument("--model-c", type=Path, required=True)
    parser.add_argument("--model-d", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=48)
    parser.add_argument("--alphas", type=float, nargs="+", required=True)
    args = parser.parse_args()

    probe = YOLO(str(args.anchor), task="classify")
    names = [probe.names[index] for index in range(len(probe.names))]
    del probe
    class_index = {name: index for index, name in enumerate(names)}
    row_index = class_index[args.class_name]
    samples = samples_for_split(args.data.resolve(), "test", class_index)
    paths = [args.anchor, args.candidate, args.model_b, args.model_c, args.model_d]
    outputs = [infer(path, samples, args.device, args.batch) for path in paths]
    if any(output[0] != names for output in outputs):
        raise SystemExit("Model class orders differ")
    labels = outputs[0][2]
    if any(not torch.equal(output[2], labels) for output in outputs[1:]):
        raise SystemExit("Sample labels differ")
    anchor_logits, candidate_logits, logits_b, logits_c, logits_d = [output[1] for output in outputs]
    calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    theta = torch.tensor(calibration["theta"], dtype=torch.float32)
    bias = torch.tensor(calibration["bias"], dtype=torch.float32)

    results = []
    for alpha in sorted(set(args.alphas)):
        if not 0 <= alpha <= 1:
            raise SystemExit(f"Alpha must be within [0, 1]: {alpha}")
        interpolated = anchor_logits.clone()
        interpolated[:, row_index] = anchor_logits[:, row_index].lerp(
            candidate_logits[:, row_index], alpha
        )
        ensemble_logits = calibrated_logits(
            feature_stack([interpolated, logits_b, logits_c, logits_d]), theta, bias
        )
        row = {"alpha": alpha, **metrics(ensemble_logits.softmax(1), labels, names)}
        results.append(row)
        print(json.dumps(row), flush=True)

    baseline = next(row for row in results if row["alpha"] == 0)
    guarded = [
        row
        for row in results
        if row["top1"] >= baseline["top1"]
        and row["macroRecall"] >= baseline["macroRecall"]
        and row["hazardousMacroRecall"] >= baseline["hazardousMacroRecall"]
        and row["knownItemBinAccuracy"] >= baseline["knownItemBinAccuracy"]
        and row["groupedKnownItemBinAccuracy"] >= baseline["groupedKnownItemBinAccuracy"]
        and row["unknownRejectionRecall"] >= baseline["unknownRejectionRecall"]
    ]
    report = {
        "anchor": str(args.anchor.resolve()),
        "candidate": str(args.candidate.resolve()),
        "className": args.class_name,
        "images": len(labels),
        "baseline": baseline,
        "guardedAlphas": [row["alpha"] for row in guarded],
        "results": results,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Guarded alphas: {report['guardedAlphas']}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
