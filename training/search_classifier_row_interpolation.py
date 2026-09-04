#!/usr/bin/env python3
"""Find the smallest safe interpolation of one classifier row."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn.functional as F
from ultralytics import YOLO

from train_new_class_rows import extract_features, merged_logits, samples_for_split


def ordered_names(model: YOLO) -> list[str]:
    return [model.names[index] for index in range(len(model.names))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--feedback-image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--feature-batch", type=int, default=64)
    parser.add_argument(
        "--alphas",
        type=float,
        nargs="+",
        default=[0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0],
    )
    args = parser.parse_args()

    anchor = YOLO(str(args.anchor), task="classify")
    candidate = YOLO(str(args.candidate), task="classify")
    names = ordered_names(anchor)
    if names != ordered_names(candidate):
        raise SystemExit("Checkpoint class order differs")
    if args.class_name not in names:
        raise SystemExit(f"Unknown class: {args.class_name}")
    class_index = {name: index for index, name in enumerate(names)}
    row_index = class_index[args.class_name]

    anchor_network = anchor.model.to(args.device).eval()
    anchor_linear = anchor_network.model[-1].linear
    candidate_linear = candidate.model.model[-1].linear
    val_samples = samples_for_split(args.data.resolve(), "val", class_index)
    val_x, val_y = extract_features(
        anchor_network,
        anchor_linear,
        val_samples,
        args.device,
        args.feature_batch,
    )
    feedback_x, feedback_y = extract_features(
        anchor_network,
        anchor_linear,
        [(args.feedback_image.resolve(), row_index)],
        args.device,
        1,
    )
    val_x, val_y = val_x.to(args.device), val_y.to(args.device)
    feedback_x, feedback_y = feedback_x.to(args.device), feedback_y.to(args.device)
    fixed_weight = anchor_linear.weight.detach().float().to(args.device)
    fixed_bias = anchor_linear.bias.detach().float().to(args.device)
    row_indices = torch.tensor([row_index], dtype=torch.long, device=args.device)
    anchor_weight = fixed_weight[row_indices].clone()
    anchor_bias = fixed_bias[row_indices].clone()
    candidate_weight = candidate_linear.weight.detach()[row_index : row_index + 1].float().to(args.device)
    candidate_bias = candidate_linear.bias.detach()[row_index : row_index + 1].float().to(args.device)

    rows = []
    eligible = []
    for alpha in sorted(set(args.alphas)):
        if not 0.0 <= alpha <= 1.0:
            raise SystemExit(f"Alpha must be in [0, 1], got {alpha}")
        weight = anchor_weight.lerp(candidate_weight, alpha)
        bias = anchor_bias.lerp(candidate_bias, alpha)
        with torch.inference_mode():
            val_logits = merged_logits(
                val_x, fixed_weight, fixed_bias, row_indices, weight, bias
            )
            feedback_logits = merged_logits(
                feedback_x, fixed_weight, fixed_bias, row_indices, weight, bias
            )
            correct = int((val_logits.argmax(1) == val_y).sum())
            nll = float(F.cross_entropy(val_logits, val_y))
            feedback_prediction = int(feedback_logits.argmax(1)[0])
            feedback_probability = float(feedback_logits.softmax(1)[0, row_index])
        row = {
            "alpha": alpha,
            "validation_correct": correct,
            "validation_images": len(val_y),
            "validation_top1": correct / len(val_y),
            "validation_nll": nll,
            "feedback_prediction": names[feedback_prediction],
            "feedback_correct": feedback_prediction == row_index,
            "feedback_target_probability": feedback_probability,
        }
        rows.append(row)
        if row["feedback_correct"]:
            eligible.append(row)
        print(json.dumps(row), flush=True)

    baseline_correct = rows[0]["validation_correct"]
    eligible = [row for row in eligible if row["validation_correct"] >= baseline_correct]
    if not eligible:
        raise SystemExit("No interpolation fixed feedback without validation top-1 regression")
    eligible.sort(
        key=lambda row: (
            -row["validation_correct"],
            row["alpha"],
            row["validation_nll"],
        )
    )
    winner_row = eligible[0]
    alpha = winner_row["alpha"]
    winner_weight = anchor_weight.lerp(candidate_weight, alpha).cpu()
    winner_bias = anchor_bias.lerp(candidate_bias, alpha).cpu()
    winner = YOLO(str(args.anchor), task="classify")
    winner_linear = winner.model.model[-1].linear
    with torch.no_grad():
        winner_linear.weight[row_index : row_index + 1] = winner_weight
        winner_linear.bias[row_index : row_index + 1] = winner_bias
    args.output.parent.mkdir(parents=True, exist_ok=True)
    winner.save(str(args.output))
    report = {
        "anchor": str(args.anchor),
        "candidate": str(args.candidate),
        "data": str(args.data),
        "class_name": args.class_name,
        "feedback_image": str(args.feedback_image),
        "winner": winner_row,
        "results": rows,
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
