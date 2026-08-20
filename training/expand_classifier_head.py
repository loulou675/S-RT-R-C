"""Expand the production classifier while preserving learned class weights."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch import nn
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
NEW_CLASS_SEEDS = {
    "dirty_plastic_bag": "plastic_bag",
    "hair_clip": "unknown",
    "hair_tie": "unknown",
    "pen_marker": "unknown",
    "phone_case": "mobile_phone",
    "plastic_cosmetic_container": "plastic_food_container",
    "plastic_cup_lid": "plastic_food_container",
}


def ordered_names(model: YOLO) -> list[str]:
    names = model.names
    return [names[index] for index in range(len(names))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=(
            ROOT
            / "training"
            / "model_archive"
            / "original-active-36class-20260820"
            / "waste_classifier.pt"
        ),
    )
    parser.add_argument(
        "--classes-file",
        type=Path,
        default=ROOT / "training" / "classes.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "training" / "checkpoints" / "waste_classifier_40_seed.pt",
    )
    args = parser.parse_args()

    source = YOLO(str(args.source), task="classify")
    expanded = YOLO(str(args.source), task="classify")
    source_names = ordered_names(source)
    expanded_names = sorted(
        json.loads(args.classes_file.read_text(encoding="utf-8"))["classes"]
    )

    source_state = source.model.state_dict()
    head_weight = "model.10.linear.weight"
    head_bias = "model.10.linear.bias"

    old_linear = expanded.model.model[-1].linear
    new_linear = nn.Linear(
        old_linear.in_features,
        len(expanded_names),
        bias=old_linear.bias is not None,
        device=old_linear.weight.device,
        dtype=old_linear.weight.dtype,
    )
    expanded.model.model[-1].linear = new_linear
    expanded_state = expanded.model.state_dict()

    source_index = {name: index for index, name in enumerate(source_names)}
    with torch.no_grad():
        for new_index, class_name in enumerate(expanded_names):
            seed_name = class_name if class_name in source_index else NEW_CLASS_SEEDS[class_name]
            old_index = source_index[seed_name]
            expanded_state[head_weight][new_index] = source_state[head_weight][old_index]
            expanded_state[head_bias][new_index] = source_state[head_bias][old_index]
            if class_name not in source_index:
                expanded_state[head_weight][new_index] += torch.randn_like(
                    expanded_state[head_weight][new_index]
                ) * 0.001

    expanded.model.load_state_dict(expanded_state, strict=True)
    expanded.model.names = {index: name for index, name in enumerate(expanded_names)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    expanded.save(str(args.output))
    print(f"Saved preserved {len(expanded_names)}-class seed: {args.output}")


if __name__ == "__main__":
    main()
