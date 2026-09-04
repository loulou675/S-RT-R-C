#!/usr/bin/env python3
"""Create a classifier checkpoint containing an ordered subset of its classes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from ultralytics import YOLO


def ordered_names(model: YOLO) -> list[str]:
    return [model.names[index] for index in range(len(model.names))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Checkpoint with the desired target head shape and architecture.",
    )
    parser.add_argument("--classes-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = YOLO(str(args.source), task="classify")
    target = YOLO(str(args.template), task="classify")
    source_names = ordered_names(source)
    target_names = json.loads(args.classes_file.read_text(encoding="utf-8"))["classes"]
    if ordered_names(target) != target_names:
        raise SystemExit("Template class order does not match classes file")
    missing = sorted(set(target_names) - set(source_names))
    if missing:
        raise SystemExit(f"Source checkpoint is missing target classes: {missing}")

    source_state = source.model.state_dict()
    target_state = target.model.state_dict()
    head_weight = "model.10.linear.weight"
    head_bias = "model.10.linear.bias"
    for key, target_value in target_state.items():
        if key in {head_weight, head_bias}:
            continue
        source_value = source_state.get(key)
        if source_value is None or source_value.shape != target_value.shape:
            raise SystemExit(f"Architecture mismatch at {key}")
        target_state[key] = source_value.detach().clone()

    source_index = {name: index for index, name in enumerate(source_names)}
    with torch.no_grad():
        for target_index, class_name in enumerate(target_names):
            source_row = source_index[class_name]
            target_state[head_weight][target_index] = source_state[head_weight][source_row]
            target_state[head_bias][target_index] = source_state[head_bias][source_row]

    target.model.load_state_dict(target_state, strict=True)
    target.model.names = {index: name for index, name in enumerate(target_names)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    target.save(str(args.output))
    print(f"Saved {len(target_names)}-class subset checkpoint: {args.output}")


if __name__ == "__main__":
    main()
