"""Train, evaluate and export the SỌRT RÁC component detector."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import onnxruntime as ort
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "training" / "component_dataset" / "data.yaml")
    parser.add_argument("--model", default="yolo26n.pt")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--export-imgsz", type=int, default=416)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--name", default="component-detector-v1")
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()

    runs = ROOT / "training" / "runs"
    trainer = YOLO(args.model)
    trainer.train(
        data=str(args.data.resolve()),
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch,
        patience=15,
        project=str(runs),
        name=args.name,
        seed=42,
        deterministic=True,
        pretrained=True,
        device=args.device,
        close_mosaic=10,
        degrees=8,
        translate=0.12,
        scale=0.35,
        fliplr=0.5,
        mixup=0.05,
    )

    run_dir = runs / args.name
    best_path = run_dir / "weights" / "best.pt"
    if not best_path.exists():
        raise SystemExit(f"Missing trained checkpoint: {best_path}")
    best = YOLO(str(best_path))
    metrics = best.val(data=str(args.data.resolve()), split="test", imgsz=args.imgsz, device=args.device)
    map50 = float(metrics.box.map50)
    map5095 = float(metrics.box.map)
    precision = float(metrics.box.mp)
    recall = float(metrics.box.mr)
    (run_dir / "component-evaluation.json").write_text(
        json.dumps({"precision": precision, "recall": recall, "map50": map50, "map50_95": map5095}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    export_path = Path(
        best.export(format="onnx", imgsz=args.export_imgsz, batch=1, dynamic=False, simplify=True, nms=True)
    )
    session = ort.InferenceSession(str(export_path), providers=["CPUExecutionProvider"])
    output_shape = session.get_outputs()[0].shape
    if len(output_shape) != 3 or output_shape[-1] != 6:
        raise SystemExit(f"Unexpected ONNX output shape {output_shape}; browser requires [1, N, 6].")

    names = best.names
    ordered_names = [names[index] for index in range(len(names))] if isinstance(names, dict) else list(names)
    configured = json.loads((ROOT / "training" / "component_classes.json").read_text(encoding="utf-8"))["modelClasses"]
    if ordered_names != configured:
        raise SystemExit(f"Class order mismatch. Model: {ordered_names}; configured: {configured}")
    labels_path = run_dir / "component_labels.json"
    labels_path.write_text(
        json.dumps({"labels": [{"index": index, "code": code} for index, code in enumerate(ordered_names)]}, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Test precision: {precision:.4f}; recall: {recall:.4f}; mAP50: {map50:.4f}; mAP50-95: {map5095:.4f}")
    print(f"Candidate model: {export_path}")
    if args.install:
        if precision < 0.65 or map50 < 0.28:
            raise SystemExit("Refusing to install: test precision or mAP50 is below the conservative baseline gate.")
        model_dir = ROOT / "public" / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(export_path, model_dir / "waste_components.onnx")
        shutil.copy2(labels_path, model_dir / "component_labels.json")
        print("Installed component detector in public/models/.")


if __name__ == "__main__":
    main()
