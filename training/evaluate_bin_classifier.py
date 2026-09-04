"""Evaluate a seven-bin classifier on core and broad-item holdouts separately."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
BROAD_PREFIX = "broad_candidate__"


def evaluate_group(
    samples: list[tuple[Path, str]],
    predicted_names: list[str],
) -> dict[str, object]:
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    correct = 0
    for (_, expected), predicted in zip(samples, predicted_names, strict=True):
        confusion[expected][predicted] += 1
        correct += predicted == expected

    per_bin = []
    for expected in sorted(confusion):
        total = sum(confusion[expected].values())
        bin_correct = confusion[expected][expected]
        per_bin.append(
            {
                "bin": expected,
                "correct": bin_correct,
                "total": total,
                "recall": round(bin_correct / total, 4),
                "predictions": dict(confusion[expected].most_common()),
            }
        )
    return {
        "images": len(samples),
        "accuracy": round(correct / len(samples), 4) if samples else None,
        "macro_recall": (
            round(sum(row["recall"] for row in per_bin) / len(per_bin), 4)
            if per_bin
            else None
        ),
        "per_bin": per_bin,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--data",
        type=Path,
        default=ROOT / "training" / "bin_dataset" / "test",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    samples: list[tuple[Path, str]] = []
    for bin_dir in sorted(path for path in args.data.iterdir() if path.is_dir()):
        samples.extend(
            (path, bin_dir.name)
            for path in sorted(bin_dir.iterdir())
            if path.suffix.lower() in IMAGE_SUFFIXES
        )
    if not samples:
        raise SystemExit(f"No test images found under {args.data}")

    model = YOLO(str(args.model), task="classify")
    options: dict[str, object] = {"imgsz": 224, "verbose": False, "stream": False}
    if args.device:
        options["device"] = args.device
    results = model.predict(source=[str(path) for path, _ in samples], **options)
    predicted_names = [model.names[int(result.probs.top1)] for result in results]

    core_indexes = [index for index, (path, _) in enumerate(samples) if not path.name.startswith(BROAD_PREFIX)]
    broad_indexes = [index for index, (path, _) in enumerate(samples) if path.name.startswith(BROAD_PREFIX)]

    def subset(indexes: list[int]) -> tuple[list[tuple[Path, str]], list[str]]:
        return [samples[index] for index in indexes], [predicted_names[index] for index in indexes]

    core_samples, core_predictions = subset(core_indexes)
    broad_samples, broad_predictions = subset(broad_indexes)
    report = {
        "model": str(args.model),
        "test_data": str(args.data),
        "all": evaluate_group(samples, predicted_names),
        "core": evaluate_group(core_samples, core_predictions),
        "broad": evaluate_group(broad_samples, broad_predictions),
    }

    output = args.output or args.model.parents[1] / "bin-evaluation.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for group_name in ("all", "core", "broad"):
        group = report[group_name]
        accuracy = group["accuracy"]
        display = f"{accuracy:.1%}" if accuracy is not None else "n/a"
        print(f"{group_name:<5}: {group['images']:>3} images, accuracy {display}")
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
