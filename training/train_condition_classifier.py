"""Train and evaluate the optional clean-versus-dirty visual classifier."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CLASSES = ["clean_empty", "dirty_residue"]


def class_recall(matrix: list[list[int]], index: int) -> float:
    total = sum(matrix[index])
    return matrix[index][index] / total if total else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "training" / "condition_dataset")
    parser.add_argument("--model", default="yolo26n-cls.pt")
    parser.add_argument("--epochs", type=int, default=70)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--name", default="condition-classifier-next")
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()

    train_classes = sorted(path.name for path in (args.data / "train").iterdir() if path.is_dir())
    if train_classes != EXPECTED_CLASSES:
        raise SystemExit(f"Condition folders must be {EXPECTED_CLASSES}; found {train_classes}")

    runs = ROOT / "training" / "runs"
    trainer = YOLO(args.model)
    trainer.train(
        data=str(args.data.resolve()),
        imgsz=224,
        epochs=args.epochs,
        batch=args.batch,
        patience=18,
        project=str(runs),
        name=args.name,
        seed=42,
        deterministic=True,
        pretrained=True,
        device=args.device,
        optimizer="AdamW",
        lr0=0.001,
        warmup_epochs=3,
        degrees=8,
        translate=0.12,
        scale=0.25,
        fliplr=0.5,
        hsv_h=0.01,
        hsv_s=0.25,
        hsv_v=0.25,
    )

    run_dir = runs / args.name
    best_path = run_dir / "weights" / "best.pt"
    if not best_path.exists():
        raise SystemExit(f"Missing trained checkpoint: {best_path}")

    best = YOLO(str(best_path))
    metrics = best.val(data=str(args.data.resolve()), split="test", imgsz=224, device=args.device)
    matrix = metrics.confusion_matrix.matrix.astype(int).tolist()
    # Ultralytics may include an extra background row/column in some versions.
    matrix = [row[:2] for row in matrix[:2]]
    recalls = {code: class_recall(matrix, index) for index, code in enumerate(EXPECTED_CLASSES)}
    accuracy = sum(matrix[index][index] for index in range(2)) / max(1, sum(sum(row) for row in matrix))
    evaluation = {
        "testAccuracy": accuracy,
        "macroRecall": sum(recalls.values()) / len(recalls),
        "perClassRecall": recalls,
        "confusionMatrix": matrix,
        "warning": "The held-out condition set is still small; treat this as an experimental signal.",
    }
    (run_dir / "condition-evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")

    export_path = Path(best.export(format="onnx", imgsz=224, batch=1, dynamic=False, simplify=True))
    names = best.names
    ordered = [names[index] for index in range(len(names))] if isinstance(names, dict) else list(names)
    if ordered != EXPECTED_CLASSES:
        raise SystemExit(f"Unexpected condition class order: {ordered}")
    labels_path = run_dir / "condition_labels.json"
    labels_path.write_text(
        json.dumps({"labels": [{"index": index, "code": code} for index, code in enumerate(ordered)]}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(evaluation, indent=2))
    print(f"Candidate model: {export_path}")
    if args.install:
        if accuracy < 0.70 or min(recalls.values()) < 0.60:
            raise SystemExit("Refusing to install: condition test accuracy/recall is below the experimental gate.")
        model_dir = ROOT / "public" / "models"
        shutil.copy2(export_path, model_dir / "waste_condition.onnx")
        shutil.copy2(labels_path, model_dir / "condition_labels.json")
        shutil.copy2(best_path, ROOT / "training" / "checkpoints" / "condition_classifier.pt")
        print("Installed condition model in public/models/.")


if __name__ == "__main__":
    main()
