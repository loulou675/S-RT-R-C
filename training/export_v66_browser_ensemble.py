#!/usr/bin/env python3
"""Export the accepted v66 41-class ensemble for ONNX Runtime Web."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
MODEL_FILES = [
    ("training/checkpoints/candidate_v64a_v29_cutlery_trained.pt", "waste_classifier.onnx"),
    ("training/checkpoints/candidate_v63b_v52_cutlery_trained.pt", "waste_classifier_v66_s_late.onnx"),
    ("training/checkpoints/candidate_v63c_v51_cutlery_trained.pt", "waste_classifier_v66_s_frozen.onnx"),
    ("training/checkpoints/candidate_v64d_v59_cutlery_trained.pt", "waste_classifier_v66_m_frozen.onnx"),
]
DEFAULT_TEMPERATURES = [1.0, 0.75, 0.75, 0.75]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint-root", type=Path, default=ROOT)
    parser.add_argument(
        "--calibration",
        type=Path,
        default=ROOT / "training" / "candidate-v66-four-model-41class-calibration.json",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "public" / "models")
    args = parser.parse_args()

    calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    class_names = None
    resolved_models = []
    for relative_checkpoint, output_name in MODEL_FILES:
        checkpoint = args.checkpoint_root / relative_checkpoint
        if not checkpoint.exists():
            raise SystemExit(f"Missing checkpoint: {checkpoint}")
        model = YOLO(str(checkpoint), task="classify")
        current_names = [model.names[index] for index in range(len(model.names))]
        if class_names is None:
            class_names = current_names
        elif current_names != class_names:
            raise SystemExit(f"Class order mismatch: {checkpoint}")
        exported = Path(
            model.export(
                format="onnx",
                imgsz=224,
                batch=1,
                dynamic=False,
                simplify=True,
                opset=17,
            )
        )
        shutil.copy2(exported, args.output / output_name)
        resolved_models.append(output_name)

    if class_names is None or len(class_names) != 41 or "disposable_cutlery" not in class_names:
        raise SystemExit("v66 export must contain all 41 classes including disposable_cutlery")
    theta = calibration["theta"]
    bias = calibration["bias"]
    if len(theta) != 4 or any(len(row) != 41 for row in theta) or len(bias) != 41:
        raise SystemExit("v66 calibration dimensions are not 4 x 41 plus 41 biases")

    runtime = {
        "version": "v66",
        "modelPaths": resolved_models,
        "temperatures": calibration.get("temperatures", DEFAULT_TEMPERATURES),
        "theta": theta,
        "bias": bias,
    }
    labels = {
        "labels": [
            {"index": index, "code": class_name}
            for index, class_name in enumerate(class_names)
        ]
    }
    (args.output / "waste_classifier_ensemble.json").write_text(
        json.dumps(runtime, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "labels.json").write_text(
        json.dumps(labels, indent=2) + "\n", encoding="utf-8"
    )
    for obsolete in args.output.glob("waste_classifier_v61_*.onnx"):
        obsolete.unlink()
    print(f"Exported v66 browser ensemble to {args.output}")


if __name__ == "__main__":
    main()
