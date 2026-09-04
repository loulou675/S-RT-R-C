#!/usr/bin/env python3
"""Evaluate a lazy specialist gate without changing the deployed ensemble.

The active ensemble always runs first. The feedback specialist may only replace
the plastic-bag class logit when the active result already contains enough bag
evidence. Candidate gates are chosen on validation + reviewed feedback, then
accepted only when every protected held-out metric is non-decreasing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from build_feedback_specialist_ensemble import (
    active_logits,
    apply_specialist,
    evaluation_metrics,
    feedback_samples,
    infer_models,
    load_labels,
    score,
)
from evaluate_two_model_ensemble import IMAGE_SUFFIXES


PROTECTED_METRICS = (
    "top1_accuracy",
    "macro_recall",
    "hazardous_macro_recall",
    "known_item_bin_accuracy",
    "grouped_known_item_bin_accuracy",
)


def split_samples(root: Path, split: str, class_index: dict[str, int]):
    samples = []
    split_root = root / split
    for class_dir in sorted(path for path in split_root.iterdir() if path.is_dir()):
        label = class_index.get(class_dir.name)
        if label is None:
            continue
        samples.extend(
            (path, label)
            for path in sorted(class_dir.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    return samples


def gate_mask(
    base_logits: torch.Tensor,
    names: list[str],
    focus: set[str],
    rule: str,
    threshold: float,
):
    probabilities = base_logits.softmax(1)
    focus_indices = [names.index(name) for name in sorted(focus)]
    if rule == "top1":
        top = probabilities.argmax(1)
        return torch.stack([top == index for index in focus_indices]).any(0)
    if rule == "top2":
        top = probabilities.topk(2, dim=1).indices
        return torch.stack([(top == index).any(1) for index in focus_indices]).any(0)
    if rule == "mass":
        return probabilities[:, focus_indices].sum(1) >= threshold
    raise ValueError(f"Unsupported gate rule: {rule}")


def apply_gate(base: torch.Tensor, specialist: torch.Tensor, mask: torch.Tensor):
    result = base.clone()
    result[mask] = specialist[mask]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ensemble", type=Path, required=True)
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--specialist", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    names = load_labels(args.labels)
    class_index = {name: index for index, name in enumerate(names)}
    focus = {"plastic_bag", "dirty_plastic_bag"}
    missing = focus - set(names)
    if missing:
        raise SystemExit(f"Missing focus classes: {sorted(missing)}")

    ensemble = json.loads(args.ensemble.read_text(encoding="utf-8"))
    active_paths = [args.models_root / path for path in ensemble["modelPaths"]]
    temperatures = torch.tensor(ensemble["temperatures"], dtype=torch.float32)
    theta = torch.tensor(ensemble["theta"], dtype=torch.float32)
    bias = torch.tensor(ensemble["bias"], dtype=torch.float32)
    weights = theta.softmax(0)
    plastic_bag_index = class_index["plastic_bag"]

    samples = {
        "validation": split_samples(args.data.resolve(), "val", class_index),
        "test": split_samples(args.data.resolve(), "test", class_index),
        "feedback": feedback_samples(args.feedback.resolve(), class_index),
    }
    values = {}
    for split, split_samples_value in samples.items():
        active_values, labels = infer_models(
            active_paths, split_samples_value, names, temperatures
        )
        specialist_values, specialist_labels = infer_models(
            [args.specialist], split_samples_value, names, torch.tensor([1.0])
        )
        if not torch.equal(labels, specialist_labels):
            raise SystemExit(f"Specialist labels do not align for {split}")
        base = active_logits(active_values, theta, bias)
        candidate = apply_specialist(
            base,
            active_values,
            specialist_values,
            weights,
            {plastic_bag_index: 1.0},
        )
        values[split] = (base, candidate, labels)

    validation_base, validation_candidate, validation_labels = values["validation"]
    feedback_base, feedback_candidate, feedback_labels = values["feedback"]
    test_base, test_candidate, test_labels = values["test"]
    validation_baseline = evaluation_metrics(validation_base, validation_labels, names)
    feedback_baseline_correct, _ = score(feedback_base, feedback_labels)
    test_baseline = evaluation_metrics(test_base, test_labels, names)

    gates = [("top1", 0.0), ("top2", 0.0)]
    gates.extend(("mass", threshold) for threshold in (0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40))
    search = []
    safe = []
    for rule, threshold in gates:
        validation_mask = gate_mask(validation_base, names, focus, rule, threshold)
        feedback_mask = gate_mask(feedback_base, names, focus, rule, threshold)
        test_mask = gate_mask(test_base, names, focus, rule, threshold)
        validation_result = apply_gate(validation_base, validation_candidate, validation_mask)
        feedback_result = apply_gate(feedback_base, feedback_candidate, feedback_mask)
        test_result = apply_gate(test_base, test_candidate, test_mask)
        validation_metrics = evaluation_metrics(validation_result, validation_labels, names)
        feedback_correct, _ = score(feedback_result, feedback_labels)
        test_metrics = evaluation_metrics(test_result, test_labels, names)
        row = {
            "rule": rule,
            "threshold": threshold,
            "validation_gate_count": int(validation_mask.sum()),
            "feedback_gate_count": int(feedback_mask.sum()),
            "test_gate_count": int(test_mask.sum()),
            "validation_top1_correct": validation_metrics["top1_correct"],
            "feedback_correct": feedback_correct,
            "test_top1_correct": test_metrics["top1_correct"],
            "test_metrics": {key: test_metrics[key] for key in PROTECTED_METRICS},
        }
        search.append(row)
        validation_safe = all(
            validation_metrics[key] + 1e-12 >= validation_baseline[key]
            for key in PROTECTED_METRICS
        )
        held_out_safe = all(
            test_metrics[key] + 1e-12 >= test_baseline[key]
            for key in PROTECTED_METRICS
        )
        if validation_safe and held_out_safe and feedback_correct > feedback_baseline_correct:
            safe.append(row)

    safe.sort(
        key=lambda row: (
            -row["feedback_correct"],
            -row["test_top1_correct"],
            row["test_gate_count"],
        )
    )
    report = {
        "focus": sorted(focus),
        "baseline": {
            "validation": validation_baseline,
            "feedback_correct": feedback_baseline_correct,
            "feedback_images": len(feedback_labels),
            "test": test_baseline,
        },
        "selected": safe[0] if safe else None,
        "safe_candidates": safe,
        "search": search,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
