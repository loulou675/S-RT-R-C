"""Train YOLO classification and install a browser-ready ONNX model plus labels."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "training" / "dataset")
    parser.add_argument("--model", default="yolo26n-cls.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default=None, help="Examples: cpu, mps, 0")
    args = parser.parse_args()

    runs = ROOT / "training" / "runs"
    trainer = YOLO(args.model)
    train_options = {
        "data": str(args.data.resolve()),
        "imgsz": 224,
        "epochs": args.epochs,
        "batch": args.batch,
        "patience": 20,
        "project": str(runs),
        "name": "waste-classifier",
        "seed": 42,
        "deterministic": True,
        "pretrained": True,
    }
    if args.device:
        train_options["device"] = args.device
    trainer.train(**train_options)

    best_path = runs / "waste-classifier" / "weights" / "best.pt"
    if not best_path.exists():
        raise SystemExit(f"Training finished but best checkpoint is missing: {best_path}")

    best = YOLO(str(best_path))
    best.val(data=str(args.data.resolve()), split="test", imgsz=224)
    exported_path = Path(best.export(format="onnx", imgsz=224, batch=1, dynamic=False, simplify=True))

    names = best.names
    ordered_names = [names[index] for index in range(len(names))] if isinstance(names, dict) else list(names)
    expected = sorted(path.name for path in (args.data / "train").iterdir() if path.is_dir() and path.name != ".DS_Store")
    configured = json.loads((ROOT / "training" / "classes.json").read_text(encoding="utf-8"))["classes"]
    if expected != sorted(configured):
        raise SystemExit("Dataset class folders do not match training/classes.json. Run sync_class_folders.py and remove obsolete class folders.")
    if ordered_names != expected:
        raise SystemExit(f"Class order mismatch. Model: {ordered_names}. Dataset folders: {expected}")

    model_dir = ROOT / "public" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exported_path, model_dir / "waste_classifier.onnx")
    labels = {"labels": [{"index": index, "code": code} for index, code in enumerate(ordered_names)]}
    (model_dir / "labels.json").write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")

    print("\nInstalled:")
    print(model_dir / "waste_classifier.onnx")
    print(model_dir / "labels.json")
    print("Run the frontend build and test with untouched test images before publishing.")


if __name__ == "__main__":
    main()
