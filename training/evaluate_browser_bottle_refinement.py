#!/usr/bin/env python3
"""Compare one replacement ensemble component with the browser image pipeline."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SPECIAL_HANDLING = {
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
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size
        size = min(width, height)
        left = (width - size) / 2
        top = (height - size) / 2
        image = image.crop((left, top, left + size, top + size)).resize(
            (224, 224), Image.Resampling.BILINEAR
        )
        values = np.asarray(image, dtype=np.float32) / 255.0
    return np.transpose(values, (2, 0, 1))[None]


def normalize_model_output(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    total = float(values.sum())
    if np.all(values >= 0) and np.all(values <= 1) and 0.98 < total < 1.02:
        return values
    return softmax(values)


def infer_component(session: ort.InferenceSession, tensor: np.ndarray) -> np.ndarray:
    output = session.run(
        [session.get_outputs()[0].name],
        {session.get_inputs()[0].name: tensor},
    )[0][0]
    return normalize_model_output(output)


def combine(component_probabilities: list[np.ndarray], config: dict) -> np.ndarray:
    log_probabilities = []
    for probabilities, temperature in zip(
        component_probabilities, config["temperatures"], strict=True
    ):
        scaled = np.log(np.clip(probabilities, 1e-12, None)) / temperature
        log_probabilities.append(np.log(np.clip(softmax(scaled), 1e-12, None)))
    stacked = np.stack(log_probabilities)
    weights = softmax(np.asarray(config["theta"], dtype=np.float32), axis=0)
    bias = np.asarray(config["bias"], dtype=np.float32)
    return softmax((weights * stacked).sum(axis=0) + bias)


def result_row(path: Path, probabilities: np.ndarray, labels: list[str]) -> dict:
    order = np.argsort(probabilities)[::-1]
    top, runner_up = int(order[0]), int(order[1])
    prediction = labels[top]
    confidence = float(probabilities[top])
    runner_up_score = float(probabilities[runner_up])
    margin = confidence - runner_up_score
    accepted = (
        prediction != "unknown"
        and confidence >= 0.55
        and margin >= 0.15
        and (prediction not in SPECIAL_HANDLING or confidence >= 0.8)
    )
    return {
        "file": path.name,
        "prediction": prediction,
        "confidence": round(confidence, 6),
        "runnerUp": labels[runner_up],
        "runnerUpScore": round(runner_up_score, 6),
        "margin": round(margin, 6),
        "appAccepted": accepted,
    }


def summarize(rows: list[dict], accepted_names: set[str], target_class: str) -> dict:
    reviewed_positive = [row for row in rows if row["file"] in accepted_names]
    reviewed_negative = [row for row in rows if row["file"] not in accepted_names]
    return {
        "reviewedBottleImages": len(reviewed_positive),
        "bottleTop1": sum(row["prediction"] == target_class for row in reviewed_positive),
        "bottleAcceptedByApp": sum(
            row["prediction"] == target_class and row["appAccepted"]
            for row in reviewed_positive
        ),
        "wrongClassAcceptedByApp": sum(
            row["prediction"] != target_class and row["appAccepted"]
            for row in reviewed_positive
        ),
        "reviewedNonBottleImages": len(reviewed_negative),
        "nonBottlePredictedAsBottle": sum(
            row["prediction"] == target_class for row in reviewed_negative
        ),
        "nonBottleAcceptedAsBottle": sum(
            row["prediction"] == target_class and row["appAccepted"]
            for row in reviewed_negative
        ),
        "positivePredictionCounts": dict(
            Counter(row["prediction"] for row in reviewed_positive).most_common()
        ),
        "negativePredictionCounts": dict(
            Counter(row["prediction"] for row in reviewed_negative).most_common()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--candidate-model", type=Path, required=True)
    parser.add_argument("--candidate-index", type=int, default=3)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--review-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.models.read_text(encoding="utf-8"))
    labels = [
        row["code"]
        for row in json.loads(args.labels.read_text(encoding="utf-8"))["labels"]
    ]
    manifest = json.loads(args.review_manifest.read_text(encoding="utf-8"))
    accepted_names = set(manifest["accepted"])
    target_class = manifest["targetClass"]
    model_dir = args.models.resolve().parent
    baseline_paths = [model_dir / path for path in config["modelPaths"]]
    if len(baseline_paths) != 4:
        raise SystemExit("Expected a four-model ensemble")
    if args.candidate_index not in range(4):
        raise SystemExit("Candidate index must be between 0 and 3")
    baseline_sessions = [
        ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        for path in baseline_paths
    ]
    candidate_session = ort.InferenceSession(
        str(args.candidate_model.resolve()), providers=["CPUExecutionProvider"]
    )
    image_paths = sorted(
        path
        for path in args.images.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    baseline_rows = []
    candidate_rows = []
    for path in image_paths:
        tensor = browser_tensor(path)
        baseline_components = [
            infer_component(session, tensor) for session in baseline_sessions
        ]
        candidate_components = list(baseline_components)
        candidate_components[args.candidate_index] = infer_component(
            candidate_session, tensor
        )
        baseline = combine(baseline_components, config)
        candidate = combine(candidate_components, config)
        baseline_rows.append(result_row(path, baseline, labels))
        candidate_rows.append(result_row(path, candidate, labels))

    report = {
        "targetClass": target_class,
        "images": str(args.images.resolve()),
        "reviewManifest": str(args.review_manifest.resolve()),
        "baselineModel": str(baseline_paths[args.candidate_index]),
        "candidateModel": str(args.candidate_model.resolve()),
        "candidateIndex": args.candidate_index,
        "baseline": summarize(baseline_rows, accepted_names, target_class),
        "candidate": summarize(candidate_rows, accepted_names, target_class),
        "rows": [
            {
                "file": baseline["file"],
                "reviewedAs": "bottle" if baseline["file"] in accepted_names else "non_bottle",
                "baseline": baseline,
                "candidate": candidate,
            }
            for baseline, candidate in zip(baseline_rows, candidate_rows, strict=True)
        ],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": report["baseline"], "candidate": report["candidate"]}, indent=2))
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
