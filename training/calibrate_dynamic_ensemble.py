#!/usr/bin/env python3
"""Cross-validate class-wise calibration for an arbitrary model ensemble."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import torch
import torch.nn.functional as F
from ultralytics import YOLO

from calibrate_four_model_ensemble import infer_any, stratified_folds
from evaluate_two_model_ensemble import samples_for_split


def parse_floats(value: str, expected: int, label: str) -> torch.Tensor:
    values = [float(item.strip()) for item in value.split(",")]
    if len(values) != expected:
        raise SystemExit(f"{label} must contain {expected} comma-separated values")
    result = torch.tensor(values, dtype=torch.float32)
    if (result <= 0).any():
        raise SystemExit(f"{label} values must be positive")
    return result


def feature_stack(logits: list[torch.Tensor], temperatures: torch.Tensor) -> torch.Tensor:
    return torch.stack(
        [F.log_softmax(value / temperature, 1) for value, temperature in zip(logits, temperatures, strict=True)],
        dim=0,
    )


def calibrated_logits(values: torch.Tensor, theta: torch.Tensor, bias: torch.Tensor) -> torch.Tensor:
    return (theta.softmax(0)[:, None, :] * values).sum(0) + bias


def train_calibrator(
    values: torch.Tensor,
    labels: torch.Tensor,
    indices: torch.Tensor,
    initial_weights: torch.Tensor,
    regularization: float,
    epochs: int = 500,
) -> tuple[torch.Tensor, torch.Tensor]:
    classes = values.shape[-1]
    theta0 = initial_weights.log()[:, None].expand(-1, classes).clone()
    theta = torch.nn.Parameter(theta0.clone())
    bias = torch.nn.Parameter(torch.zeros(classes))
    optimizer = torch.optim.Adam([theta, bias], lr=0.03)
    best_loss = math.inf
    best: tuple[torch.Tensor, torch.Tensor] | None = None
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
    if best is None:
        raise RuntimeError("Calibration did not produce a result")
    return best


def metric(logits: torch.Tensor, labels: torch.Tensor) -> tuple[int, float, float]:
    correct = int((logits.argmax(1) == labels).sum())
    return correct, correct / len(labels), float(F.cross_entropy(logits, labels))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, nargs="+", required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--temperatures", required=True)
    parser.add_argument("--initial-weights", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=48)
    args = parser.parse_args()

    count = len(args.models)
    temperatures = parse_floats(args.temperatures, count, "temperatures")
    initial_weights = parse_floats(args.initial_weights, count, "initial-weights")
    initial_weights /= initial_weights.sum()

    probe = YOLO(str(args.models[0]), task="classify")
    names = [probe.names[index] for index in range(len(probe.names))]
    del probe
    class_index = {name: index for index, name in enumerate(names)}
    samples = samples_for_split(args.data.resolve(), "val", class_index)
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
        raise SystemExit("No validation labels were loaded")

    values = feature_stack(all_logits, temperatures)
    theta0 = initial_weights.log()[:, None].expand(-1, len(names))
    base_logits = calibrated_logits(values, theta0, torch.zeros(len(names)))
    base_correct, base_top1, base_nll = metric(base_logits, labels)
    folds = stratified_folds(labels)
    all_indices = torch.arange(len(labels))
    rows = []
    for regularization in (0.3, 1.0, 3.0, 10.0, 30.0, 100.0):
        out_of_fold = torch.empty(len(labels), len(names))
        for held_out in folds:
            mask = torch.ones(len(labels), dtype=torch.bool)
            mask[held_out] = False
            theta, bias = train_calibrator(
                values, labels, all_indices[mask], initial_weights, regularization
            )
            out_of_fold[held_out] = calibrated_logits(values[:, held_out], theta, bias)
        correct, top1, nll = metric(out_of_fold, labels)
        rows.append(
            {
                "regularization": regularization,
                "correct": correct,
                "images": len(labels),
                "top1": top1,
                "nll": nll,
            }
        )
        print(f"regularization={regularization:g} cv_top1={top1:.4%} ({correct}/{len(labels)}) nll={nll:.5f}")
    rows.sort(key=lambda row: (-row["correct"], row["nll"], -row["regularization"]))
    winner = rows[0]
    theta, bias = train_calibrator(
        values, labels, all_indices, initial_weights, winner["regularization"]
    )
    payload = {
        "models": [str(path) for path in args.models],
        "temperatures": temperatures.tolist(),
        "initial_weights": initial_weights.tolist(),
        "selected_regularization": winner["regularization"],
        "cross_validation": winner,
        "all_cross_validation_results": rows,
        "base": {
            "correct": base_correct,
            "images": len(labels),
            "top1": base_top1,
            "nll": base_nll,
        },
        "theta": theta.tolist(),
        "bias": bias.tolist(),
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"base={base_top1:.4%} ({base_correct}/{len(labels)})")
    print(f"best_cv={winner['top1']:.4%} ({winner['correct']}/{len(labels)})")
    print(f"Saved calibration: {args.output}")


if __name__ == "__main__":
    main()
