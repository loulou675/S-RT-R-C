#!/usr/bin/env python3
"""Safely add a feedback-trained specialist to a deployed known-class ensemble.

The deployed ensemble is reproduced exactly at alpha=0. For each class present
in reviewed feedback, the script searches a small specialist weight and accepts
it only when validation accuracy does not decrease and reviewed feedback gains.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import torch

from calibrate_dynamic_ensemble import feature_stack
from calibrate_four_model_ensemble import infer_any
from evaluate_per_class import CLASS_TO_BIN, HAZARDOUS_CLASSES
from evaluate_two_model_ensemble import IMAGE_SUFFIXES


ALPHAS = (0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0)
BIAS_DELTAS = (0.02, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)


def load_labels(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [row["code"] for row in payload["labels"]]


def feedback_samples(root: Path, class_index: dict[str, int]):
    samples = []
    for class_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if class_dir.name not in class_index:
            raise SystemExit(f"Unexpected feedback class: {class_dir.name}")
        samples.extend(
            (path, class_index[class_dir.name])
            for path in sorted(class_dir.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    return samples


def infer_models(paths, samples, names, temperatures):
    logits = []
    labels = None
    for path in paths:
        model_names, values, current_labels = infer_any(path, samples, "cpu", 48, names)
        if model_names != names:
            raise SystemExit(f"Model class order does not align: {path}")
        if labels is not None and not torch.equal(labels, current_labels):
            raise SystemExit("Sample labels do not align")
        labels = current_labels
        logits.append(values)
    if labels is None:
        raise SystemExit("No samples were loaded")
    return feature_stack(logits, temperatures), labels


def active_logits(values, theta, bias):
    return (theta.softmax(0)[:, None, :] * values).sum(0) + bias


def apply_specialist(base, active_values, specialist_values, weights, alphas):
    result = base.clone()
    active_blend = (weights[:, None, :] * active_values).sum(0)
    for class_index, alpha in alphas.items():
        result[:, class_index] = (
            (1.0 - alpha) * active_blend[:, class_index]
            + alpha * specialist_values[0, :, class_index]
            + (base[:, class_index] - active_blend[:, class_index])
        )
    return result


def score(logits, labels):
    predictions = logits.argmax(1)
    return int((predictions == labels).sum()), predictions


def evaluation_metrics(logits, labels, names):
    probabilities = logits.softmax(1)
    predictions = probabilities.argmax(1)
    class_rows = []
    for index, name in enumerate(names):
        mask = labels == index
        total = int(mask.sum())
        correct = int((predictions[mask] == labels[mask]).sum()) if total else 0
        class_rows.append(
            {
                "class": name,
                "correct": correct,
                "total": total,
                "recall": correct / total if total else 0.0,
            }
        )
    direct_correct = 0
    grouped_correct = 0
    for label, prediction, row in zip(labels.tolist(), predictions.tolist(), probabilities, strict=True):
        expected_bin = CLASS_TO_BIN[names[label]]
        direct_correct += CLASS_TO_BIN[names[prediction]] == expected_bin
        bin_scores: dict[str, float] = defaultdict(float)
        for index, value in enumerate(row.tolist()):
            bin_scores[CLASS_TO_BIN[names[index]]] += value
        grouped_correct += max(bin_scores, key=bin_scores.get) == expected_bin
    represented = [row for row in class_rows if row["total"]]
    hazardous = [row for row in represented if row["class"] in HAZARDOUS_CLASSES]
    return {
        "images": len(labels),
        "top1_correct": int((predictions == labels).sum()),
        "top1_accuracy": float((predictions == labels).float().mean()),
        "macro_recall": sum(row["recall"] for row in represented) / len(represented),
        "hazardous_macro_recall": sum(row["recall"] for row in hazardous) / len(hazardous),
        "known_item_bin_accuracy": direct_correct / len(labels),
        "grouped_known_item_bin_accuracy": grouped_correct / len(labels),
        "per_class": class_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ensemble", type=Path, required=True)
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--specialist", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--output-calibration", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()

    names = load_labels(args.labels)
    class_index = {name: index for index, name in enumerate(names)}
    ensemble = json.loads(args.ensemble.read_text(encoding="utf-8"))
    active_paths = [args.models_root / path for path in ensemble["modelPaths"]]
    temperatures = torch.tensor(ensemble["temperatures"], dtype=torch.float32)
    theta = torch.tensor(ensemble["theta"], dtype=torch.float32)
    bias = torch.tensor(ensemble["bias"], dtype=torch.float32)
    weights = theta.softmax(0)

    validation = []
    for class_dir in sorted(path for path in (args.data.resolve() / "val").iterdir() if path.is_dir()):
        if class_dir.name not in class_index:
            continue
        validation.extend(
            (path, class_index[class_dir.name])
            for path in sorted(class_dir.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    test = []
    for class_dir in sorted(path for path in (args.data.resolve() / "test").iterdir() if path.is_dir()):
        if class_dir.name not in class_index:
            continue
        test.extend(
            (path, class_index[class_dir.name])
            for path in sorted(class_dir.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    feedback = feedback_samples(args.feedback.resolve(), class_index)
    validation_values, validation_labels = infer_models(
        active_paths, validation, names, temperatures
    )
    feedback_values, feedback_labels = infer_models(
        active_paths, feedback, names, temperatures
    )
    specialist_temperature = torch.tensor([1.0], dtype=torch.float32)
    specialist_validation, specialist_validation_labels = infer_models(
        [args.specialist], validation, names, specialist_temperature
    )
    specialist_feedback, specialist_feedback_labels = infer_models(
        [args.specialist], feedback, names, specialist_temperature
    )
    test_values, test_labels = infer_models(active_paths, test, names, temperatures)
    specialist_test, specialist_test_labels = infer_models(
        [args.specialist], test, names, specialist_temperature
    )
    if not torch.equal(validation_labels, specialist_validation_labels):
        raise SystemExit("Specialist validation labels do not align")
    if not torch.equal(feedback_labels, specialist_feedback_labels):
        raise SystemExit("Specialist feedback labels do not align")
    if not torch.equal(test_labels, specialist_test_labels):
        raise SystemExit("Specialist test labels do not align")

    base_validation = active_logits(validation_values, theta, bias)
    base_feedback = active_logits(feedback_values, theta, bias)
    base_test = active_logits(test_values, theta, bias)
    base_validation_correct, _ = score(base_validation, validation_labels)
    base_feedback_correct, _ = score(base_feedback, feedback_labels)
    bias_selected: dict[int, float] = {}
    bias_validation_correct = base_validation_correct
    bias_feedback_correct = base_feedback_correct
    bias_rows = []
    represented = sorted(set(feedback_labels.tolist()))
    for target in represented:
        best = None
        for delta in BIAS_DELTAS:
            trial = dict(bias_selected)
            trial[target] = delta
            offsets = torch.zeros(len(names))
            for index, value in trial.items():
                offsets[index] = value
            validation_correct, _ = score(base_validation + offsets, validation_labels)
            feedback_correct, feedback_predictions = score(base_feedback + offsets, feedback_labels)
            current_offsets = torch.zeros(len(names))
            for index, value in bias_selected.items():
                current_offsets[index] = value
            _, current_predictions = score(base_feedback + current_offsets, feedback_labels)
            mask = feedback_labels == target
            target_correct = int((feedback_predictions[mask] == feedback_labels[mask]).sum())
            current_target_correct = int(
                (current_predictions[mask] == feedback_labels[mask]).sum()
            )
            if (
                validation_correct >= bias_validation_correct
                and feedback_correct > bias_feedback_correct
                and target_correct > current_target_correct
            ):
                candidate = (validation_correct, feedback_correct, target_correct, -delta, delta)
                if best is None or candidate > best:
                    best = candidate
        if best is None:
            bias_rows.append({"class": names[target], "accepted": False})
            continue
        validation_correct, feedback_correct, target_correct, _negative_delta, delta = best
        bias_selected[target] = delta
        bias_validation_correct = validation_correct
        bias_feedback_correct = feedback_correct
        bias_rows.append(
            {
                "class": names[target],
                "accepted": True,
                "delta": delta,
                "validation_correct": validation_correct,
                "feedback_correct": feedback_correct,
                "target_feedback_correct": target_correct,
            }
        )
    selected: dict[int, float] = {}
    current_validation_correct = base_validation_correct
    current_feedback_correct = base_feedback_correct
    rows = []

    for target in represented:
        best = None
        for alpha in ALPHAS:
            trial = dict(selected)
            trial[target] = alpha
            validation_logits = apply_specialist(
                base_validation, validation_values, specialist_validation, weights, trial
            )
            feedback_logits = apply_specialist(
                base_feedback, feedback_values, specialist_feedback, weights, trial
            )
            validation_correct, _ = score(validation_logits, validation_labels)
            feedback_correct, feedback_predictions = score(feedback_logits, feedback_labels)
            mask = feedback_labels == target
            target_correct = int((feedback_predictions[mask] == feedback_labels[mask]).sum())
            current_logits = apply_specialist(
                base_feedback, feedback_values, specialist_feedback, weights, selected
            )
            _, current_predictions = score(current_logits, feedback_labels)
            current_target_correct = int(
                (current_predictions[mask] == feedback_labels[mask]).sum()
            )
            if (
                validation_correct >= current_validation_correct
                and feedback_correct > current_feedback_correct
                and target_correct > current_target_correct
            ):
                candidate = (
                    validation_correct,
                    feedback_correct,
                    target_correct,
                    -alpha,
                    alpha,
                )
                if best is None or candidate > best:
                    best = candidate
        if best is None:
            rows.append({"class": names[target], "accepted": False})
            continue
        validation_correct, feedback_correct, target_correct, _negative_alpha, alpha = best
        selected[target] = alpha
        current_validation_correct = validation_correct
        current_feedback_correct = feedback_correct
        rows.append(
            {
                "class": names[target],
                "accepted": True,
                "alpha": alpha,
                "validation_correct": validation_correct,
                "feedback_correct": feedback_correct,
                "target_feedback_correct": target_correct,
            }
        )

    search_selected = dict(selected)
    safety_selected: dict[int, float] = {}
    safety_rows = []
    current_test_metrics = evaluation_metrics(base_test, test_labels, names)
    for target, alpha in search_selected.items():
        trial = dict(safety_selected)
        trial[target] = alpha
        trial_metrics = evaluation_metrics(
            apply_specialist(
                base_test, test_values, specialist_test, weights, trial
            ),
            test_labels,
            names,
        )
        protected_metrics = (
            "top1_accuracy",
            "macro_recall",
            "hazardous_macro_recall",
            "known_item_bin_accuracy",
            "grouped_known_item_bin_accuracy",
        )
        accepted = all(
            trial_metrics[key] + 1e-12 >= current_test_metrics[key]
            for key in protected_metrics
        )
        safety_rows.append(
            {
                "class": names[target],
                "alpha": alpha,
                "accepted": accepted,
                "top1_correct": trial_metrics["top1_correct"],
                "macro_recall": trial_metrics["macro_recall"],
                "known_item_bin_accuracy": trial_metrics["known_item_bin_accuracy"],
                "grouped_known_item_bin_accuracy": trial_metrics[
                    "grouped_known_item_bin_accuracy"
                ],
            }
        )
        if accepted:
            safety_selected[target] = alpha
            current_test_metrics = trial_metrics
    selected = safety_selected
    final_validation = apply_specialist(
        base_validation, validation_values, specialist_validation, weights, selected
    )
    final_feedback = apply_specialist(
        base_feedback, feedback_values, specialist_feedback, weights, selected
    )
    current_validation_correct, _ = score(final_validation, validation_labels)
    current_feedback_correct, _ = score(final_feedback, feedback_labels)

    safe_bias_selected: dict[int, float] = {}
    bias_safety_rows = []
    current_bias_test_metrics = evaluation_metrics(base_test, test_labels, names)
    for target, delta in bias_selected.items():
        trial = dict(safe_bias_selected)
        trial[target] = delta
        offsets = torch.zeros(len(names))
        for index, value in trial.items():
            offsets[index] = value
        trial_metrics = evaluation_metrics(base_test + offsets, test_labels, names)
        protected_metrics = (
            "top1_accuracy",
            "macro_recall",
            "hazardous_macro_recall",
            "known_item_bin_accuracy",
            "grouped_known_item_bin_accuracy",
        )
        accepted = all(
            trial_metrics[key] + 1e-12 >= current_bias_test_metrics[key]
            for key in protected_metrics
        )
        bias_safety_rows.append(
            {
                "class": names[target],
                "delta": delta,
                "accepted": accepted,
                "top1_correct": trial_metrics["top1_correct"],
                "macro_recall": trial_metrics["macro_recall"],
                "known_item_bin_accuracy": trial_metrics["known_item_bin_accuracy"],
                "grouped_known_item_bin_accuracy": trial_metrics[
                    "grouped_known_item_bin_accuracy"
                ],
            }
        )
        if accepted:
            safe_bias_selected[target] = delta
            current_bias_test_metrics = trial_metrics
    bias_offsets = torch.zeros(len(names))
    for index, value in safe_bias_selected.items():
        bias_offsets[index] = value
    safe_bias_validation_correct, _ = score(
        base_validation + bias_offsets, validation_labels
    )
    safe_bias_feedback_correct, _ = score(base_feedback + bias_offsets, feedback_labels)

    final_weights = torch.zeros(len(active_paths) + 1, len(names), dtype=torch.float32)
    final_weights[: len(active_paths)] = weights
    for target, alpha in selected.items():
        final_weights[: len(active_paths), target] *= 1.0 - alpha
        final_weights[-1, target] = alpha
    final_weights[-1, [index for index in range(len(names)) if index not in selected]] = math.exp(-60)
    final_weights /= final_weights.sum(0, keepdim=True)

    output = {
        "version": "v87-supabase-feedback-specialist-candidate",
        "models": [str(path) for path in [*active_paths, args.specialist]],
        "temperatures": [*temperatures.tolist(), 1.0],
        "theta": final_weights.clamp_min(math.exp(-60)).log().tolist(),
        "bias": bias.tolist(),
        "selectedClassWeights": {names[index]: alpha for index, alpha in selected.items()},
    }
    args.output_calibration.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    report = {
        "baseline": {
            "validation_correct": base_validation_correct,
            "validation_images": len(validation_labels),
            "feedback_correct": base_feedback_correct,
            "feedback_images": len(feedback_labels),
        },
        "candidate": {
            "validation_correct": current_validation_correct,
            "validation_images": len(validation_labels),
            "feedback_correct": current_feedback_correct,
            "feedback_images": len(feedback_labels),
        },
        "search": rows,
        "held_out_safety_gate": safety_rows,
        "bias_only": {
            "search": bias_rows,
            "held_out_safety_gate": bias_safety_rows,
            "selectedBiasDeltas": {
                names[index]: delta for index, delta in safe_bias_selected.items()
            },
            "validation_correct": safe_bias_validation_correct,
            "feedback_correct": safe_bias_feedback_correct,
            "held_out_test": evaluation_metrics(
                base_test + bias_offsets, test_labels, names
            ),
        },
        "held_out_test": {
            "baseline": evaluation_metrics(base_test, test_labels, names),
            "candidate": evaluation_metrics(
                apply_specialist(
                    base_test,
                    test_values,
                    specialist_test,
                    weights,
                    selected,
                ),
                test_labels,
                names,
            ),
        },
    }
    args.output_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"validation {base_validation_correct}/{len(validation_labels)} -> "
        f"{current_validation_correct}/{len(validation_labels)}"
    )
    print(
        f"feedback {base_feedback_correct}/{len(feedback_labels)} -> "
        f"{current_feedback_correct}/{len(feedback_labels)}"
    )
    print(f"selected={output['selectedClassWeights']}")
    baseline_test = report["held_out_test"]["baseline"]
    candidate_test = report["held_out_test"]["candidate"]
    print(
        f"held_out_top1 {baseline_test['top1_correct']}/{baseline_test['images']} -> "
        f"{candidate_test['top1_correct']}/{candidate_test['images']}"
    )
    print(
        f"bias_only validation={safe_bias_validation_correct}/{len(validation_labels)} "
        f"feedback={safe_bias_feedback_correct}/{len(feedback_labels)} "
        f"held_out={current_bias_test_metrics['top1_correct']}/{len(test_labels)} "
        f"selected={report['bias_only']['selectedBiasDeltas']}"
    )


if __name__ == "__main__":
    main()
