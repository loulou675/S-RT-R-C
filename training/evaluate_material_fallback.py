#!/usr/bin/env python3
"""Evaluate a material model only on images rejected by original v66."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from build_material_dataset import ITEM_TO_MATERIAL, IMAGE_SUFFIXES


HAZARDOUS_CLASSES = {
    "aerosol_can",
    "battery",
    "chemical_container",
    "electronic_cable",
    "light_bulb",
    "mobile_phone",
    "power_bank",
}


def softmax(values: np.ndarray, axis: int = -1) -> np.ndarray:
    shifted = values - values.max(axis=axis, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum(axis=axis, keepdims=True)


def browser_tensor(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        image = source.convert("RGB")
        width, height = image.size
        size = min(width, height)
        left = (width - size) / 2
        top = (height - size) / 2
        image = image.crop((left, top, left + size, top + size)).resize(
            (224, 224), Image.Resampling.BILINEAR
        )
        values = np.asarray(image, dtype=np.float32) / 255.0
    return np.transpose(values, (2, 0, 1))[None]


def samples_for_split(data: Path, split: str):
    samples = []
    for class_dir in sorted(path for path in (data / split).iterdir() if path.is_dir()):
        for path in sorted(class_dir.iterdir()):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                samples.append((path, class_dir.name, ITEM_TO_MATERIAL[class_dir.name]))
    return samples


def infer(path: Path, samples) -> np.ndarray:
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    rows = [
        session.run([output_name], {input_name: browser_tensor(image_path)})[0][0]
        for image_path, _, _ in samples
    ]
    values = np.asarray(rows, dtype=np.float32)
    totals = values.sum(axis=1)
    if np.all(values >= 0) and np.all(values <= 1) and np.all((totals > 0.98) & (totals < 1.02)):
        return values
    return softmax(values)


def combine_v66(model_probabilities: list[np.ndarray], calibration: dict) -> np.ndarray:
    log_probabilities = []
    for probabilities, temperature in zip(
        model_probabilities, calibration["temperatures"], strict=True
    ):
        scaled = np.log(np.clip(probabilities, 1e-12, None)) / temperature
        log_probabilities.append(np.log(np.clip(softmax(scaled), 1e-12, None)))
    stacked = np.stack(log_probabilities)
    theta = np.asarray(calibration["theta"], dtype=np.float32)
    weights = softmax(theta, axis=0)
    bias = np.asarray(calibration["bias"], dtype=np.float32)
    logits = (weights[:, None, :] * stacked).sum(axis=0) + bias
    return softmax(logits)


def original_v66_acceptance(probabilities: np.ndarray, labels: list[str]) -> np.ndarray:
    ranking = np.argsort(probabilities, axis=1)[:, ::-1]
    top = ranking[:, 0]
    second = ranking[:, 1]
    confidence = probabilities[np.arange(len(probabilities)), top]
    margin = confidence - probabilities[np.arange(len(probabilities)), second]
    names = np.asarray(labels)[top]
    special_ok = np.asarray([
        name not in HAZARDOUS_CLASSES or score >= 0.8
        for name, score in zip(names, confidence, strict=True)
    ])
    return (names != "unknown") & (confidence >= 0.55) & (margin >= 0.15) & special_ok


def evaluate_material(
    samples,
    exact_accepted: np.ndarray,
    material_probabilities: np.ndarray,
    material_labels: list[str],
    thresholds: tuple[float, float, float],
):
    confidence_min, margin_min, electronic_min = thresholds
    ranking = np.argsort(material_probabilities, axis=1)[:, ::-1]
    top = ranking[:, 0]
    second = ranking[:, 1]
    confidence = material_probabilities[np.arange(len(samples)), top]
    margin = confidence - material_probabilities[np.arange(len(samples)), second]
    predictions = np.asarray(material_labels)[top]
    expected = np.asarray([material for _, _, material in samples])
    rejected = ~exact_accepted
    accepted = rejected & (confidence >= confidence_min) & (margin >= margin_min)
    accepted &= (predictions != "electronic_battery") | (confidence >= electronic_min)
    correct = predictions == expected

    predicted_electronic = accepted & (predictions == "electronic_battery")
    electronic_predictions = int(predicted_electronic.sum())
    electronic_correct = int((predicted_electronic & correct).sum())
    rejected_count = int(rejected.sum())
    accepted_count = int(accepted.sum())
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for expected_name, predicted_name, is_rejected, is_accepted in zip(
        expected, predictions, rejected, accepted, strict=True
    ):
        if is_rejected:
            confusion[str(expected_name)][str(predicted_name) if is_accepted else "not_accepted"] += 1

    return {
        "thresholds": {
            "confidence": confidence_min,
            "margin": margin_min,
            "electronicConfidence": electronic_min,
        },
        "images": len(samples),
        "exactV66Accepted": int(exact_accepted.sum()),
        "exactV66Rejected": rejected_count,
        "materialAccepted": accepted_count,
        "rejectedImageCoverage": accepted_count / rejected_count if rejected_count else 0,
        "acceptedMaterialPrecision": int((accepted & correct).sum()) / accepted_count if accepted_count else 0,
        "correctFallbacks": int((accepted & correct).sum()),
        "electronicPredictions": electronic_predictions,
        "electronicPrecision": electronic_correct / electronic_predictions if electronic_predictions else 1,
        "remainingWithoutResult": rejected_count - accepted_count,
        "confusionOnV66Rejected": {name: dict(rows) for name, rows in sorted(confusion.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--item-model", type=Path, action="append", required=True)
    parser.add_argument("--item-labels", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--material-model", type=Path, required=True)
    parser.add_argument("--material-labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if len(args.item_model) != 4:
        raise SystemExit("Exactly four v66 item models are required")
    item_labels = [row["code"] for row in json.loads(args.item_labels.read_text())["labels"]]
    material_labels = [row["code"] for row in json.loads(args.material_labels.read_text())["labels"]]
    calibration = json.loads(args.calibration.read_text())
    split_values = {}

    for split in ("val", "test"):
        samples = samples_for_split(args.data, split)
        item_probabilities = [infer(path, samples) for path in args.item_model]
        combined = combine_v66(item_probabilities, calibration)
        exact_accepted = original_v66_acceptance(combined, item_labels)
        material_probabilities = infer(args.material_model, samples)
        split_values[split] = (samples, exact_accepted, material_probabilities)

    candidates = []
    for thresholds in product(
        (0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95),
        (0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.40),
        (0.70, 0.75, 0.80, 0.85, 0.90, 0.95),
    ):
        row = evaluate_material(*split_values["val"], material_labels, thresholds)
        candidates.append(row)

    eligible = [
        row for row in candidates
        if row["acceptedMaterialPrecision"] >= 0.85 and row["electronicPrecision"] >= 0.90
    ]
    ranked = eligible or candidates
    ranked.sort(key=lambda row: (-row["correctFallbacks"], -row["acceptedMaterialPrecision"], -row["rejectedImageCoverage"]))
    selected = ranked[0]
    thresholds = (
        selected["thresholds"]["confidence"],
        selected["thresholds"]["margin"],
        selected["thresholds"]["electronicConfidence"],
    )
    report = {
        "selectionRule": {
            "minimumAcceptedMaterialPrecision": 0.85,
            "minimumElectronicPredictionPrecision": 0.90,
            "objective": "maximum correct material fallbacks on v66-rejected validation images",
        },
        "validation": selected,
        "heldoutTest": evaluate_material(*split_values["test"], material_labels, thresholds),
        "topCandidates": ranked[:12],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["heldoutTest"], indent=2))


if __name__ == "__main__":
    main()
