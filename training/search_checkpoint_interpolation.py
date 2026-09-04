#!/usr/bin/env python3
"""Search validation accuracy along the line between two YOLO checkpoints."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import torch
from ultralytics import YOLO


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def ordered_names(model: YOLO) -> list[str]:
    return [model.names[index] for index in range(len(model.names))]


def validation_samples(data: Path) -> list[tuple[Path, str]]:
    samples: list[tuple[Path, str]] = []
    for class_dir in sorted(path for path in (data / "val").iterdir() if path.is_dir()):
        samples.extend(
            (path, class_dir.name)
            for path in sorted(class_dir.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    return samples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument(
        "--alphas",
        type=float,
        nargs="+",
        default=[0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5],
    )
    args = parser.parse_args()

    anchor = YOLO(str(args.anchor), task="classify")
    candidate = YOLO(str(args.candidate), task="classify")
    if ordered_names(anchor) != ordered_names(candidate):
        raise SystemExit("Checkpoint class order differs; interpolation is unsafe")

    anchor_state = {
        key: value.detach().clone() for key, value in anchor.model.state_dict().items()
    }
    candidate_state = candidate.model.state_dict()
    if anchor_state.keys() != candidate_state.keys():
        raise SystemExit("Checkpoint state dictionaries differ")
    for key in anchor_state:
        if anchor_state[key].shape != candidate_state[key].shape:
            raise SystemExit(f"Checkpoint tensor shape differs for {key}")

    samples = validation_samples(args.data.resolve())
    if not samples:
        raise SystemExit("Validation split is empty")
    sources = [str(path) for path, _ in samples]
    expected = [class_name for _, class_name in samples]

    rows: list[dict[str, float | int]] = []
    best_accuracy = -1.0
    best_alpha = None
    best_state = None
    for alpha in sorted(set(args.alphas)):
        if not 0.0 <= alpha <= 1.0:
            raise SystemExit(f"Alpha must be in [0, 1], got {alpha}")
        blended = {}
        for key, anchor_value in anchor_state.items():
            candidate_value = candidate_state[key]
            if torch.is_floating_point(anchor_value):
                blended[key] = anchor_value.lerp(candidate_value, alpha)
            else:
                blended[key] = anchor_value
        # Ultralytics fuses convolution and batch-normalization layers on the
        # first predict call. Use a fresh unfused model for every alpha so the
        # next interpolation can still load the original state-dict layout.
        evaluation_model = YOLO(str(args.anchor), task="classify")
        evaluation_model.model.load_state_dict(blended, strict=True)
        results = evaluation_model.predict(
            source=sources,
            imgsz=224,
            batch=args.batch,
            device=args.device,
            verbose=False,
            stream=False,
        )
        correct = sum(
            evaluation_model.names[int(result.probs.top1)] == class_name
            for result, class_name in zip(results, expected, strict=True)
        )
        accuracy = correct / len(samples)
        rows.append({"alpha": alpha, "correct": correct, "images": len(samples), "top1": accuracy})
        print(f"alpha={alpha:.3f} validation_top1={accuracy:.4%} ({correct}/{len(samples)})")
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_alpha = alpha
            best_state = {key: value.detach().clone() for key, value in blended.items()}

    if best_state is None or best_alpha is None:
        raise SystemExit("No interpolation candidate was evaluated")
    winner = YOLO(str(args.anchor), task="classify")
    winner.model.load_state_dict(best_state, strict=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    winner.save(str(args.output))
    report_path = args.output.with_suffix(".json")
    report_path.write_text(
        json.dumps(
            {
                "anchor": str(args.anchor),
                "candidate": str(args.candidate),
                "data": str(args.data),
                "best_alpha": best_alpha,
                "best_validation_top1": best_accuracy,
                "results": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Saved best interpolation: {args.output}")
    print(f"Saved report: {report_path}")


if __name__ == "__main__":
    main()
