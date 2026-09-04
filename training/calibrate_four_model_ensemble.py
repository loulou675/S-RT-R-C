#!/usr/bin/env python3
"""Cross-validate class-wise weights for a fixed four-model ensemble."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
import torch.nn.functional as F
from ultralytics import YOLO

from evaluate_browser_bottle_refinement import browser_tensor, infer_component
from evaluate_two_model_ensemble import infer, samples_for_split


INITIAL_WEIGHTS = torch.tensor([0.50, 0.15, 0.15, 0.20], dtype=torch.float32)
TEMPERATURES = torch.tensor([1.0, 0.75, 0.75, 0.75], dtype=torch.float32)


def feature_stack(logits: list[torch.Tensor]) -> torch.Tensor:
    return torch.stack(
        [F.log_softmax(value / temperature, 1) for value, temperature in zip(logits, TEMPERATURES)],
        dim=0,
    )


def calibrated_logits(values, theta, bias):
    return (theta.softmax(0)[:, None, :] * values).sum(0) + bias


def train_calibrator(values, labels, indices, regularization, epochs=500):
    classes = values.shape[-1]
    theta0 = INITIAL_WEIGHTS.log()[:, None].expand(-1, classes).clone()
    theta = torch.nn.Parameter(theta0.clone())
    bias = torch.nn.Parameter(torch.zeros(classes))
    optimizer = torch.optim.Adam([theta, bias], lr=0.03)
    best_loss = math.inf
    best = None
    stale = 0
    for _epoch in range(epochs):
        logits = calibrated_logits(values[:, indices], theta, bias)
        supervised = F.cross_entropy(logits, labels[indices])
        penalty = (theta - theta0).square().mean() + bias.square().mean()
        loss = supervised + regularization * penalty
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        current = float(loss.detach())
        if current < best_loss - 1e-7:
            best_loss = current
            best = (theta.detach().clone(), bias.detach().clone())
            stale = 0
        else:
            stale += 1
        if stale >= 40:
            break
    return best


def stratified_folds(labels, count=5):
    folds = [[] for _ in range(count)]
    for class_index in labels.unique(sorted=True).tolist():
        indices = torch.where(labels == class_index)[0].tolist()
        for position, index in enumerate(indices):
            folds[(position + class_index) % count].append(index)
    return [torch.tensor(sorted(fold), dtype=torch.long) for fold in folds]


def metric(logits, labels):
    correct = int((logits.argmax(1) == labels).sum())
    return correct, correct / len(labels), float(F.cross_entropy(logits, labels))


def infer_any(model_path, samples, device, batch_size, names):
    """Run trainable checkpoints or fixed-batch browser ONNX exports."""
    if model_path.suffix.lower() != ".onnx":
        return infer(model_path, samples, device, batch_size)

    session = ort.InferenceSession(
        str(model_path.resolve()), providers=["CPUExecutionProvider"]
    )
    probabilities = [
        infer_component(session, browser_tensor(path)) for path, _label in samples
    ]
    # feature_stack expects logits. Log-probabilities are equivalent logits up
    # to an additive constant and preserve the deployed browser preprocessing.
    logits = torch.from_numpy(
        np.stack([np.log(np.clip(row, 1e-12, None)) for row in probabilities])
    ).float()
    labels = torch.tensor([label for _path, label in samples], dtype=torch.long)
    return names, logits, labels


def main() -> None:
    parser = argparse.ArgumentParser()
    for letter in "abcd":
        parser.add_argument(f"--model-{letter}", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", choices=["val", "test"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=48)
    parser.add_argument("--calibration", type=Path)
    args = parser.parse_args()

    paths = [args.model_a, args.model_b, args.model_c, args.model_d]
    probe = YOLO(str(paths[0]), task="classify")
    names = [probe.names[index] for index in range(len(probe.names))]
    del probe
    class_index = {name: index for index, name in enumerate(names)}
    samples = samples_for_split(args.data.resolve(), args.split, class_index)
    all_logits = []
    labels = None
    for path in paths:
        model_names, logits, current_labels = infer_any(
            path, samples, args.device, args.batch, names
        )
        if model_names != names:
            raise SystemExit("Model class orders do not align")
        if labels is not None and not torch.equal(labels, current_labels):
            raise SystemExit("Sample labels do not align")
        labels = current_labels
        all_logits.append(logits)
    values = feature_stack(all_logits)
    theta0 = INITIAL_WEIGHTS.log()[:, None].expand(-1, len(names))
    base_logits = calibrated_logits(values, theta0, torch.zeros(len(names)))
    base_correct, base_top1, base_nll = metric(base_logits, labels)

    if args.calibration:
        saved = json.loads(args.calibration.read_text(encoding="utf-8"))
        theta = torch.tensor(saved["theta"], dtype=torch.float32)
        bias = torch.tensor(saved["bias"], dtype=torch.float32)
        logits = calibrated_logits(values, theta, bias)
        correct, top1, nll = metric(logits, labels)
        report = {
            "split": args.split,
            "calibration": str(args.calibration),
            "base": {"correct": base_correct, "images": len(labels), "top1": base_top1, "nll": base_nll},
            "calibrated": {"correct": correct, "images": len(labels), "top1": top1, "nll": nll},
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"base={base_top1:.4%} ({base_correct}/{len(labels)})")
        print(f"calibrated={top1:.4%} ({correct}/{len(labels)})")
        print(f"Saved: {args.output}")
        return

    if args.split != "val":
        raise SystemExit("Calibration fitting is allowed only on --split val")
    folds = stratified_folds(labels)
    all_indices = torch.arange(len(labels))
    rows = []
    for regularization in (0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0):
        out_of_fold = torch.empty(len(labels), len(names))
        for held_out in folds:
            mask = torch.ones(len(labels), dtype=torch.bool)
            mask[held_out] = False
            theta, bias = train_calibrator(values, labels, all_indices[mask], regularization)
            out_of_fold[held_out] = calibrated_logits(values[:, held_out], theta, bias)
        correct, top1, nll = metric(out_of_fold, labels)
        row = {"regularization": regularization, "correct": correct, "images": len(labels), "top1": top1, "nll": nll}
        rows.append(row)
        print(f"regularization={regularization:g} cv_top1={top1:.4%} ({correct}/{len(labels)}) nll={nll:.5f}")
    rows.sort(key=lambda row: (-row["correct"], row["nll"], -row["regularization"]))
    winner = rows[0]
    theta, bias = train_calibrator(values, labels, all_indices, winner["regularization"])
    payload = {
        "models": [str(path) for path in paths],
        "temperatures": TEMPERATURES.tolist(),
        "initial_weights": INITIAL_WEIGHTS.tolist(),
        "selected_regularization": winner["regularization"],
        "cross_validation": winner,
        "all_cross_validation_results": rows,
        "theta": theta.tolist(),
        "bias": bias.tolist(),
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"base={base_top1:.4%} ({base_correct}/{len(labels)})")
    print(f"best_cv={winner['top1']:.4%} ({winner['correct']}/{len(labels)})")
    print(f"Saved calibration: {args.output}")


if __name__ == "__main__":
    main()
