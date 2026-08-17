"""Evaluate a classifier with the same confidence gates used by the web app."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ultralytics import YOLO

from evaluate_per_class import CLASS_TO_BIN, HAZARDOUS_CLASSES, IMAGE_SUFFIXES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--min-margin", type=float, default=0.15)
    parser.add_argument("--special-confidence", type=float, default=0.8)
    args = parser.parse_args()

    samples = [
        (image, class_dir.name)
        for class_dir in sorted(path for path in args.data.iterdir() if path.is_dir())
        for image in sorted(class_dir.iterdir())
        if image.suffix.lower() in IMAGE_SUFFIXES
    ]
    if not samples:
        raise SystemExit(f"No images found under {args.data}")

    model = YOLO(str(args.model), task="classify")
    predict_options = {"imgsz": 224, "verbose": False, "stream": False}
    if args.model.suffix.lower() == ".onnx":
        # Browser exports use a fixed batch size of one.
        results = [
            model.predict(source=str(path), **predict_options)[0]
            for path, _ in samples
        ]
    else:
        results = model.predict(
            source=[str(path) for path, _ in samples],
            **predict_options,
        )

    known_total = accepted = accepted_item_correct = accepted_bin_correct = 0
    false_confident_bins = 0
    unknown_total = unknown_rejected = 0

    for (_, expected), result in zip(samples, results, strict=True):
        probabilities = result.probs.data.detach().cpu().tolist()
        ranking = sorted(range(len(probabilities)), key=probabilities.__getitem__, reverse=True)
        top_index, second_index = ranking[:2]
        predicted = model.names[top_index]
        confidence = float(probabilities[top_index])
        margin = confidence - float(probabilities[second_index])
        is_accepted = (
            predicted != "unknown"
            and confidence >= args.min_confidence
            and margin >= args.min_margin
            and (predicted not in HAZARDOUS_CLASSES or confidence >= args.special_confidence)
        )

        if expected == "unknown":
            unknown_total += 1
            if not is_accepted:
                unknown_rejected += 1
            continue

        known_total += 1
        if not is_accepted:
            continue
        accepted += 1
        if predicted == expected:
            accepted_item_correct += 1
        if CLASS_TO_BIN[predicted] == CLASS_TO_BIN[expected]:
            accepted_bin_correct += 1
        else:
            false_confident_bins += 1

    report = {
        "model": str(args.model),
        "data": str(args.data),
        "known_images": known_total,
        "accepted": accepted,
        "coverage": round(accepted / known_total, 4) if known_total else None,
        "accepted_item_precision": round(accepted_item_correct / accepted, 4) if accepted else None,
        "accepted_bin_precision": round(accepted_bin_correct / accepted, 4) if accepted else None,
        "false_confident_bin_errors": false_confident_bins,
        "unknown_images": unknown_total,
        "unknown_rejection": round(unknown_rejected / unknown_total, 4) if unknown_total else None,
        "thresholds": {
            "confidence": args.min_confidence,
            "margin": args.min_margin,
            "special_confidence": args.special_confidence,
        },
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
