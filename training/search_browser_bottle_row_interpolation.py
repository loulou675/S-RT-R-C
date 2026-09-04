#!/usr/bin/env python3
"""Select a conservative browser-safe interpolation of a bottle classifier row."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from ultralytics import YOLO

from evaluate_browser_bottle_refinement import (
    IMAGE_SUFFIXES,
    browser_tensor,
    combine,
    infer_component,
    result_row,
    softmax,
    summarize,
)


def interpolate_target_probability(
    anchor: np.ndarray,
    candidate: np.ndarray,
    target_index: int,
    alpha: float,
) -> np.ndarray:
    reference_index = 0 if target_index != 0 else 1
    epsilon = 1e-12
    target_delta = (
        np.log(max(float(candidate[target_index]), epsilon))
        - np.log(max(float(candidate[reference_index]), epsilon))
        - np.log(max(float(anchor[target_index]), epsilon))
        + np.log(max(float(anchor[reference_index]), epsilon))
    )
    logits = np.log(np.clip(anchor, epsilon, None))
    logits[target_index] += alpha * target_delta
    return softmax(logits)


def ordered_names(model: YOLO) -> list[str]:
    return [model.names[index] for index in range(len(model.names))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor-checkpoint", type=Path, required=True)
    parser.add_argument("--candidate-checkpoint", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--candidate-onnx", type=Path, required=True)
    parser.add_argument("--candidate-index", type=int, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--review-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--alphas",
        type=float,
        nargs="+",
        default=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    )
    args = parser.parse_args()

    config = json.loads(args.models.read_text(encoding="utf-8"))
    labels = [
        row["code"]
        for row in json.loads(args.labels.read_text(encoding="utf-8"))["labels"]
    ]
    manifest = json.loads(args.review_manifest.read_text(encoding="utf-8"))
    target_class = manifest["targetClass"]
    target_index = labels.index(target_class)
    accepted_names = set(manifest["accepted"])
    model_dir = args.models.resolve().parent
    model_paths = [model_dir / path for path in config["modelPaths"]]
    if args.candidate_index not in range(len(model_paths)):
        raise SystemExit("Candidate index is outside the ensemble")
    baseline_sessions = [
        ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        for path in model_paths
    ]
    candidate_session = ort.InferenceSession(
        str(args.candidate_onnx.resolve()), providers=["CPUExecutionProvider"]
    )
    image_paths = sorted(
        path
        for path in args.images.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    cached = []
    for path in image_paths:
        tensor = browser_tensor(path)
        components = [infer_component(session, tensor) for session in baseline_sessions]
        candidate = infer_component(candidate_session, tensor)
        cached.append((path, components, candidate))

    results = []
    rows_by_alpha = {}
    for alpha in sorted(set(args.alphas)):
        if not 0 <= alpha <= 1:
            raise SystemExit(f"Alpha must be within [0, 1]: {alpha}")
        rows = []
        for path, components, candidate in cached:
            interpolated = list(components)
            interpolated[args.candidate_index] = interpolate_target_probability(
                components[args.candidate_index], candidate, target_index, alpha
            )
            rows.append(result_row(path, combine(interpolated, config), labels))
        summary = summarize(rows, accepted_names, target_class)
        summary["alpha"] = alpha
        results.append(summary)
        rows_by_alpha[alpha] = rows
        print(json.dumps(summary), flush=True)

    baseline = next(row for row in results if row["alpha"] == 0)
    eligible = [
        row
        for row in results
        if row["nonBottleAcceptedAsBottle"] <= baseline["nonBottleAcceptedAsBottle"]
        and row["wrongClassAcceptedByApp"] <= baseline["wrongClassAcceptedByApp"]
    ]
    if not eligible:
        raise SystemExit("No interpolation satisfies the false-positive guardrails")
    eligible.sort(
        key=lambda row: (
            -row["bottleAcceptedByApp"],
            -row["bottleTop1"],
            row["wrongClassAcceptedByApp"],
            row["alpha"],
        )
    )
    winner = eligible[0]
    alpha = winner["alpha"]

    anchor = YOLO(str(args.anchor_checkpoint), task="classify")
    candidate = YOLO(str(args.candidate_checkpoint), task="classify")
    names = ordered_names(anchor)
    if names != ordered_names(candidate) or names != labels:
        raise SystemExit("Checkpoint/browser label order differs")
    row_index = names.index(target_class)
    anchor_linear = anchor.model.model[-1].linear
    candidate_linear = candidate.model.model[-1].linear
    with torch.no_grad():
        anchor_linear.weight[row_index] = anchor_linear.weight[row_index].lerp(
            candidate_linear.weight[row_index], alpha
        )
        anchor_linear.bias[row_index] = anchor_linear.bias[row_index].lerp(
            candidate_linear.bias[row_index], alpha
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    anchor.save(str(args.output))
    report = {
        "anchorCheckpoint": str(args.anchor_checkpoint.resolve()),
        "candidateCheckpoint": str(args.candidate_checkpoint.resolve()),
        "candidateIndex": args.candidate_index,
        "targetClass": target_class,
        "selectionRule": {
            "guardrails": [
                "non-bottle accepted-as-bottle does not exceed v69",
                "accepted wrong-class results on reviewed bottles do not exceed v69",
            ],
            "objective": "maximize accepted correct bottles, then bottle top-1, then use the smallest alpha",
        },
        "baseline": baseline,
        "winner": winner,
        "results": results,
        "winnerRows": rows_by_alpha[alpha],
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Selected alpha={alpha}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
