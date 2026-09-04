#!/usr/bin/env python3
"""Select or evaluate a deterministic two-classifier ensemble."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from ultralytics import YOLO
from ultralytics.data.augment import classify_transforms

from train_stable_classify_head import ImageDataset, keep_batch_norm_frozen


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def samples_for_split(data: Path, split: str, class_index: dict[str, int]):
    samples = []
    for class_dir in sorted(path for path in (data / split).iterdir() if path.is_dir()):
        if class_dir.name not in class_index:
            raise SystemExit(f"Unexpected class folder: {class_dir.name}")
        samples.extend(
            (path, class_index[class_dir.name])
            for path in sorted(class_dir.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    return samples


def infer(model_path: Path, samples, device: str, batch_size: int):
    model = YOLO(str(model_path), task="classify")
    names = [model.names[index] for index in range(len(model.names))]
    loader = DataLoader(
        ImageDataset(samples, classify_transforms(224)),
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
    )
    network = model.model.to(device).eval()
    # Ultralytics classification heads return an inference tuple while in eval
    # mode. Put only the head on its tensor-returning path, then explicitly keep
    # every batch-normalization layer frozen for deterministic scoring.
    network.model[-1].train()
    keep_batch_norm_frozen(network)
    logits = []
    labels = []
    with torch.inference_mode():
        for images, batch_labels, _ in loader:
            logits.append(network(images.to(device)).float().cpu())
            labels.append(batch_labels.long())
    del network, model
    if device == "mps":
        torch.mps.empty_cache()
    return names, torch.cat(logits), torch.cat(labels)


def combine(a, b, weight_b: float, temperature_b: float, mode: str):
    if mode == "probability":
        return (1.0 - weight_b) * F.softmax(a, 1) + weight_b * F.softmax(b / temperature_b, 1)
    return (1.0 - weight_b) * a + weight_b * (b / temperature_b)


def score(values, labels):
    predictions = values.argmax(1)
    correct = int((predictions == labels).sum())
    loss = float(F.cross_entropy(values, labels))
    return correct, correct / len(labels), loss


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-a", type=Path, required=True)
    parser.add_argument("--model-b", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", choices=["val", "test"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--weight-b", type=float)
    parser.add_argument("--temperature-b", type=float)
    parser.add_argument("--mode", choices=["probability", "logit"])
    args = parser.parse_args()

    probe = YOLO(str(args.model_a), task="classify")
    names = [probe.names[index] for index in range(len(probe.names))]
    del probe
    class_index = {name: index for index, name in enumerate(names)}
    samples = samples_for_split(args.data.resolve(), args.split, class_index)
    names_a, logits_a, labels_a = infer(args.model_a, samples, args.device, args.batch)
    names_b, logits_b, labels_b = infer(args.model_b, samples, args.device, args.batch)
    if names_a != names_b or names_a != names or not torch.equal(labels_a, labels_b):
        raise SystemExit("Model class order or sample labels do not align")

    baseline_correct, baseline_top1, baseline_loss = score(logits_a, labels_a)
    if args.weight_b is not None:
        if args.temperature_b is None or args.mode is None:
            raise SystemExit("Fixed evaluation requires --temperature-b and --mode")
        configurations = [(args.weight_b, args.temperature_b, args.mode)]
    else:
        configurations = [
            (weight / 100.0, temperature, mode)
            for mode in ("probability", "logit")
            for temperature in (0.75, 1.0, 1.25, 1.5, 2.0)
            for weight in range(5, 51, 5)
        ]

    rows = []
    for weight_b, temperature_b, mode in configurations:
        combined = combine(logits_a, logits_b, weight_b, temperature_b, mode)
        correct, top1, loss = score(combined, labels_a)
        rows.append({
            "weight_b": weight_b,
            "temperature_b": temperature_b,
            "mode": mode,
            "correct": correct,
            "images": len(labels_a),
            "top1": top1,
            "cross_entropy": loss,
        })
    rows.sort(key=lambda row: (-row["correct"], row["cross_entropy"], row["weight_b"]))
    report = {
        "model_a": str(args.model_a),
        "model_b": str(args.model_b),
        "data": str(args.data),
        "split": args.split,
        "baseline_a": {
            "correct": baseline_correct,
            "images": len(labels_a),
            "top1": baseline_top1,
            "cross_entropy": baseline_loss,
        },
        "best": rows[0],
        "top_configurations": rows[:20],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"baseline_a={baseline_top1:.4%} ({baseline_correct}/{len(labels_a)})")
    print(f"best={rows[0]['top1']:.4%} ({rows[0]['correct']}/{len(labels_a)}) {rows[0]}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
