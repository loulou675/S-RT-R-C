#!/usr/bin/env python3
"""Export the accepted v61 classifier ensemble for ONNX Runtime Web."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = ROOT / "training" / "candidate-v61-four-model-classwise-calibration.json"
OUTPUT = ROOT / "public" / "models"
MODELS = [
    (ROOT / "training/checkpoints/candidate_v29_weak_group_focused_rows.pt", "waste_classifier.onnx"),
    (ROOT / "training/runs/candidate-v52-yolo26s-late-block/weights/epoch5.pt", "waste_classifier_v61_s_late.onnx"),
    (ROOT / "training/checkpoints/candidate_v51_yolo26s_frozen_head.pt", "waste_classifier_v61_s_frozen.onnx"),
    (ROOT / "training/checkpoints/candidate_v59_yolo26m_frozen_head.pt", "waste_classifier_v61_m_frozen.onnx"),
]


def main() -> None:
    calibration = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for checkpoint, output_name in MODELS:
        if not checkpoint.exists():
            raise SystemExit(f"Missing checkpoint: {checkpoint}")
        exported = Path(
            YOLO(str(checkpoint), task="classify").export(
                format="onnx",
                imgsz=224,
                batch=1,
                dynamic=False,
                simplify=True,
                opset=17,
            )
        )
        shutil.copy2(exported, OUTPUT / output_name)

    runtime = {
        "version": "v61",
        "modelPaths": [output_name for _, output_name in MODELS],
        "temperatures": calibration["temperatures"],
        "theta": calibration["theta"],
        "bias": calibration["bias"],
    }
    (OUTPUT / "waste_classifier_ensemble.json").write_text(
        json.dumps(runtime, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Exported v61 browser ensemble to {OUTPUT}")


if __name__ == "__main__":
    main()
