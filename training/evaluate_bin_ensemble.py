"""Tune and evaluate the item-plus-bin ensemble used by the web app."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ultralytics import YOLO

try:
    from evaluate_per_class import CLASS_TO_BIN
except ModuleNotFoundError:
    from training.evaluate_per_class import CLASS_TO_BIN


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
BROAD_PREFIX = "broad_candidate__"


def load_samples(data: Path) -> list[tuple[Path, str]]:
    samples: list[tuple[Path, str]] = []
    for bin_dir in sorted(path for path in data.iterdir() if path.is_dir()):
        samples.extend(
            (path, bin_dir.name)
            for path in sorted(bin_dir.iterdir())
            if path.suffix.lower() in IMAGE_SUFFIXES
        )
    return samples


def predict_probabilities(
    model: YOLO,
    paths: list[Path],
    device: str | None,
) -> list[dict[str, float]]:
    options: dict[str, object] = {"imgsz": 224, "verbose": False, "stream": False}
    if device:
        options["device"] = device
    results = model.predict(source=[str(path) for path in paths], **options)
    rows = []
    for result in results:
        rows.append(
            {
                model.names[index]: float(score)
                for index, score in enumerate(result.probs.data.tolist())
            }
        )
    return rows


def ensemble_prediction(
    item_scores: dict[str, float],
    bin_scores: dict[str, float],
    direct_weight: float,
) -> str:
    item_bin_scores = {code: 0.0 for code in bin_scores}
    for item_code, score in item_scores.items():
        bin_code = CLASS_TO_BIN[item_code]
        item_bin_scores[bin_code] = item_bin_scores.get(bin_code, 0.0) + score
    return max(
        bin_scores,
        key=lambda code: direct_weight * bin_scores[code]
        + (1 - direct_weight) * item_bin_scores.get(code, 0.0),
    )


def accuracy(
    samples: list[tuple[Path, str]],
    item_rows: list[dict[str, float]],
    bin_rows: list[dict[str, float]],
    weight: float,
) -> float:
    if not samples:
        return 0.0
    correct = sum(
        ensemble_prediction(item_scores, bin_scores, weight) == expected
        for (_, expected), item_scores, bin_scores in zip(samples, item_rows, bin_rows, strict=True)
    )
    return correct / len(samples)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--item-model", type=Path, required=True)
    parser.add_argument("--bin-model", type=Path, required=True)
    parser.add_argument("--tune-data", type=Path, default=ROOT / "training" / "bin_dataset" / "val")
    parser.add_argument("--test-data", type=Path, default=ROOT / "training" / "bin_dataset" / "test")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default=None)
    parser.add_argument("--fixed-weight", type=float, default=None)
    args = parser.parse_args()

    item_model = YOLO(str(args.item_model), task="classify")
    bin_model = YOLO(str(args.bin_model), task="classify")
    tune_samples = load_samples(args.tune_data)
    test_samples = load_samples(args.test_data)
    tune_paths = [path for path, _ in tune_samples]
    test_paths = [path for path, _ in test_samples]

    tune_item = predict_probabilities(item_model, tune_paths, args.device)
    tune_bin = predict_probabilities(bin_model, tune_paths, args.device)
    candidate_weights = [index / 100 for index in range(101)]
    weight_scores = [
        (accuracy(tune_samples, tune_item, tune_bin, weight), weight)
        for weight in candidate_weights
    ]
    best_validation, best_weight = max(weight_scores, key=lambda row: (row[0], -abs(row[1] - 0.49)))
    if args.fixed_weight is not None:
        best_weight = min(1.0, max(0.0, args.fixed_weight))
        best_validation = accuracy(tune_samples, tune_item, tune_bin, best_weight)

    test_item = predict_probabilities(item_model, test_paths, args.device)
    test_bin = predict_probabilities(bin_model, test_paths, args.device)
    core_indexes = [index for index, (path, _) in enumerate(test_samples) if not path.name.startswith(BROAD_PREFIX)]
    broad_indexes = [index for index, (path, _) in enumerate(test_samples) if path.name.startswith(BROAD_PREFIX)]

    def subset(indexes: list[int]):
        return (
            [test_samples[index] for index in indexes],
            [test_item[index] for index in indexes],
            [test_bin[index] for index in indexes],
        )

    core_samples, core_item, core_bin = subset(core_indexes)
    broad_samples, broad_item, broad_bin = subset(broad_indexes)
    report = {
        "item_model": str(args.item_model),
        "bin_model": str(args.bin_model),
        "direct_bin_weight": best_weight,
        "validation_images": len(tune_samples),
        "validation_accuracy": round(best_validation, 6),
        "test_images": len(test_samples),
        "test_accuracy": round(accuracy(test_samples, test_item, test_bin, best_weight), 6),
        "core_test_images": len(core_samples),
        "core_test_accuracy": round(accuracy(core_samples, core_item, core_bin, best_weight), 6),
        "broad_test_images": len(broad_samples),
        "broad_test_accuracy": round(accuracy(broad_samples, broad_item, broad_bin, best_weight), 6),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
