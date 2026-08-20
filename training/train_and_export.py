"""Train YOLO classification and install a browser-ready ONNX model plus labels."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

# Ultralytics imports Polars for the first time when saving an epoch. On some
# macOS/cloud-backed filesystems that late binary load can time out after a long
# MPS training epoch. Load it before training so a dependency problem fails fast
# and completed epochs are not lost.
import polars  # noqa: F401
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "training" / "classifier_dataset")
    parser.add_argument("--model", default="yolo26n-cls.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr0", type=float, default=None)
    parser.add_argument("--warmup-epochs", type=float, default=None)
    parser.add_argument("--warmup-bias-lr", type=float, default=None)
    parser.add_argument(
        "--optimizer",
        default=None,
        help="Ultralytics optimizer name, for example AdamW or SGD. Defaults to auto.",
    )
    parser.add_argument("--freeze", type=int, default=None)
    parser.add_argument(
        "--save-period",
        type=int,
        default=-1,
        help="Save an epoch checkpoint every N epochs. Use 1 for controlled top-1 selection.",
    )
    parser.add_argument("--device", default=None, help="Examples: cpu, mps, 0")
    parser.add_argument("--name", default="waste-classifier-next")
    parser.add_argument("--classes-file", type=Path, default=ROOT / "training" / "classes.json")
    parser.add_argument("--install-model-name", default="waste_classifier.onnx")
    parser.add_argument("--install-labels-name", default="labels.json")
    parser.add_argument("--install", action="store_true", help="Replace the model used by the web app")
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
        "name": args.name,
        "seed": 42,
        "deterministic": True,
        "pretrained": True,
        "save_period": args.save_period,
    }
    if args.device:
        train_options["device"] = args.device
    if args.lr0 is not None:
        train_options["lr0"] = args.lr0
    if args.warmup_epochs is not None:
        train_options["warmup_epochs"] = args.warmup_epochs
    if args.warmup_bias_lr is not None:
        train_options["warmup_bias_lr"] = args.warmup_bias_lr
    if args.optimizer is not None:
        train_options["optimizer"] = args.optimizer
    if args.freeze is not None:
        train_options["freeze"] = args.freeze
    trainer.train(**train_options)

    run_dir = runs / args.name
    best_path = run_dir / "weights" / "best.pt"
    if not best_path.exists():
        raise SystemExit(f"Training finished but best checkpoint is missing: {best_path}")

    # Ultralytics classification fitness is primarily top-5 accuracy, which is
    # not the acceptance metric for this project. When epoch checkpoints are
    # available, select the highest validation top-1 checkpoint explicitly.
    selected_path = best_path
    results_path = run_dir / "results.csv"
    if args.save_period == 1 and results_path.exists():
        with results_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if rows:
            top1_row = max(rows, key=lambda row: float(row["metrics/accuracy_top1"]))
            epoch_number = int(float(top1_row["epoch"]))
            epoch_path = run_dir / "weights" / f"epoch{epoch_number - 1}.pt"
            if epoch_path.exists():
                selected_path = epoch_path
                print(
                    f"Selected epoch {epoch_number} by validation top-1 "
                    f"({float(top1_row['metrics/accuracy_top1']):.3%})."
                )

    best = YOLO(str(selected_path))
    best.val(data=str(args.data.resolve()), split="test", imgsz=224)
    exported_path = Path(best.export(format="onnx", imgsz=224, batch=1, dynamic=False, simplify=True))

    names = best.names
    ordered_names = [names[index] for index in range(len(names))] if isinstance(names, dict) else list(names)
    expected = sorted(path.name for path in (args.data / "train").iterdir() if path.is_dir() and path.name != ".DS_Store")
    configured = json.loads(args.classes_file.read_text(encoding="utf-8"))["classes"]
    if expected != sorted(configured):
        raise SystemExit("Dataset class folders do not match training/classes.json. Run sync_class_folders.py and remove obsolete class folders.")
    if ordered_names != expected:
        raise SystemExit(f"Class order mismatch. Model: {ordered_names}. Dataset folders: {expected}")

    labels = {"labels": [{"index": index, "code": code} for index, code in enumerate(ordered_names)]}
    (run_dir / "labels.json").write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")

    print("\nCandidate model:")
    print(exported_path)
    print(run_dir / "labels.json")
    if args.install:
        model_dir = ROOT / "public" / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exported_path, model_dir / args.install_model_name)
        shutil.copy2(run_dir / "labels.json", model_dir / args.install_labels_name)
        print("\nInstalled in the web app:")
        print(model_dir / args.install_model_name)
        print(model_dir / args.install_labels_name)
    else:
        print("Model was not installed. Evaluate it first, then rerun with --install if it improves.")


if __name__ == "__main__":
    main()
