#!/usr/bin/env python3
"""Train only the final classifier while preserving the active feature extractor.

The backbone and all batch-normalization statistics remain in evaluation mode.
This avoids the representation drift observed when Ultralytics fine-tuning was
run on the expanded dataset. Candidate selection uses validation top-1 only.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset
from ultralytics import YOLO
from ultralytics.data.augment import classify_transforms


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class ImageDataset(Dataset):
    def __init__(self, samples: list[tuple[Path, int]], transform) -> None:
        self.samples = samples
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        path, label = self.samples[index]
        with Image.open(path) as image:
            tensor = self.transform(image.convert("RGB"))
        return tensor, label, path.name.startswith("expansion_")


@dataclass(frozen=True)
class Configuration:
    learning_rate: float
    class_weight_exponent: float
    expansion_weight: float
    distillation_weight: float


def ordered_names(model: YOLO) -> list[str]:
    return [model.names[index] for index in range(len(model.names))]


def samples_for_split(data: Path, split: str, class_index: dict[str, int]):
    samples: list[tuple[Path, int]] = []
    for class_dir in sorted(path for path in (data / split).iterdir() if path.is_dir()):
        if class_dir.name not in class_index:
            raise SystemExit(f"Unexpected class folder: {class_dir.name}")
        samples.extend(
            (path, class_index[class_dir.name])
            for path in sorted(class_dir.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    return samples


def extract_features(
    network: nn.Module,
    linear: nn.Linear,
    samples: list[tuple[Path, int]],
    device: str,
    batch_size: int,
):
    dataset = ImageDataset(samples, classify_transforms(224))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    feature_batches: list[torch.Tensor] = []
    label_batches: list[torch.Tensor] = []
    expansion_batches: list[torch.Tensor] = []
    captured: list[torch.Tensor] = []

    def capture_features(_module, inputs) -> None:
        captured.append(inputs[0].detach())

    handle = linear.register_forward_pre_hook(capture_features)
    network.eval()
    with torch.inference_mode():
        for images, labels, expansion in loader:
            captured.clear()
            network(images.to(device))
            if len(captured) != 1:
                raise RuntimeError("Expected one classifier feature batch")
            feature_batches.append(captured[0].float().cpu())
            label_batches.append(labels.long())
            expansion_batches.append(expansion.bool())
    handle.remove()
    return (
        torch.cat(feature_batches),
        torch.cat(label_batches),
        torch.cat(expansion_batches),
    )


def evaluate(features: torch.Tensor, labels: torch.Tensor, layer: nn.Linear) -> tuple[int, float]:
    with torch.inference_mode():
        predicted = layer(features).argmax(dim=1)
    correct = int((predicted == labels).sum())
    return correct, correct / len(labels)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--feature-batch", type=int, default=64)
    parser.add_argument("--train-batch", type=int, default=512)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--lr", type=float, default=0.0002)
    parser.add_argument(
        "--learning-rates",
        type=float,
        nargs="+",
        default=None,
        help="Optional learning-rate grid. Overrides --lr when supplied.",
    )
    parser.add_argument("--class-weight-exponents", type=float, nargs="+", default=[0.0, 0.25])
    parser.add_argument("--expansion-weights", type=float, nargs="+", default=[3.0, 6.0])
    parser.add_argument("--distillation-weights", type=float, nargs="+", default=[0.8, 0.95])
    parser.add_argument(
        "--focus-classes",
        nargs="*",
        default=[],
        help="Only expansion images from these classes receive expansion weighting.",
    )
    args = parser.parse_args()

    torch.manual_seed(42)
    random.seed(42)
    model = YOLO(str(args.model), task="classify")
    names = ordered_names(model)
    class_index = {name: index for index, name in enumerate(names)}
    data = args.data.resolve()
    train_samples = samples_for_split(data, "train", class_index)
    val_samples = samples_for_split(data, "val", class_index)
    if not train_samples or not val_samples:
        raise SystemExit("Training and validation splits must be non-empty")

    network = model.model.to(args.device).eval()
    source_linear = network.model[-1].linear
    train_x, train_y, train_expansion = extract_features(
        network, source_linear, train_samples, args.device, args.feature_batch
    )
    val_x, val_y, _ = extract_features(
        network, source_linear, val_samples, args.device, args.feature_batch
    )
    train_x = train_x.to(args.device)
    train_y = train_y.to(args.device)
    train_expansion = train_expansion.to(args.device)
    if args.focus_classes:
        unknown_focus = sorted(set(args.focus_classes) - set(class_index))
        if unknown_focus:
            raise SystemExit(f"Unknown focus classes: {unknown_focus}")
        focus_indices = torch.tensor(
            [class_index[name] for name in args.focus_classes], device=args.device
        )
        train_expansion &= (train_y[:, None] == focus_indices[None, :]).any(dim=1)
    val_x = val_x.to(args.device)
    val_y = val_y.to(args.device)

    anchor_weight = source_linear.weight.detach().float().clone().to(args.device)
    anchor_bias = source_linear.bias.detach().float().clone().to(args.device)
    with torch.inference_mode():
        anchor_logits = F.linear(train_x, anchor_weight, anchor_bias)
    class_counts = torch.bincount(train_y, minlength=len(names)).float()
    configurations = [
        Configuration(learning_rate, class_exponent, expansion_weight, distillation_weight)
        for learning_rate in (args.learning_rates or [args.lr])
        for class_exponent in args.class_weight_exponents
        for expansion_weight in args.expansion_weights
        for distillation_weight in args.distillation_weights
    ]

    baseline_layer = nn.Linear(source_linear.in_features, source_linear.out_features).to(args.device)
    with torch.no_grad():
        baseline_layer.weight.copy_(anchor_weight)
        baseline_layer.bias.copy_(anchor_bias)
    baseline_correct, baseline_accuracy = evaluate(val_x, val_y, baseline_layer)
    print(
        f"baseline validation_top1={baseline_accuracy:.4%} "
        f"({baseline_correct}/{len(val_y)})"
    )

    report_rows = []
    global_best_accuracy = baseline_accuracy
    global_best_state = copy.deepcopy(baseline_layer.state_dict())
    global_best_configuration = None
    global_best_epoch = 0

    for configuration_index, configuration in enumerate(configurations, start=1):
        layer = nn.Linear(source_linear.in_features, source_linear.out_features).to(args.device)
        with torch.no_grad():
            layer.weight.copy_(anchor_weight)
            layer.bias.copy_(anchor_bias)
        optimizer = torch.optim.AdamW(
            layer.parameters(), lr=configuration.learning_rate, weight_decay=0.0
        )
        class_weights = class_counts.clamp_min(1).pow(-configuration.class_weight_exponent)
        class_weights /= class_weights.mean()
        sample_weights = class_weights[train_y] * torch.where(
            train_expansion,
            torch.tensor(configuration.expansion_weight, device=args.device),
            torch.tensor(1.0, device=args.device),
        )
        generator = torch.Generator().manual_seed(42)
        best_accuracy = baseline_accuracy
        best_correct = baseline_correct
        best_epoch = 0
        best_state = copy.deepcopy(layer.state_dict())
        stale_epochs = 0

        for epoch in range(1, args.epochs + 1):
            permutation = torch.randperm(len(train_y), generator=generator).to(args.device)
            layer.train()
            for start in range(0, len(train_y), args.train_batch):
                indices = permutation[start : start + args.train_batch]
                logits = layer(train_x[indices])
                supervised = F.cross_entropy(logits, train_y[indices], reduction="none")
                supervised = (supervised * sample_weights[indices]).sum() / sample_weights[indices].sum()
                distillation = F.kl_div(
                    F.log_softmax(logits / 2.0, dim=1),
                    F.softmax(anchor_logits[indices] / 2.0, dim=1),
                    reduction="batchmean",
                ) * 4.0
                loss = (
                    (1.0 - configuration.distillation_weight) * supervised
                    + configuration.distillation_weight * distillation
                )
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            layer.eval()
            correct, accuracy = evaluate(val_x, val_y, layer)
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_correct = correct
                best_epoch = epoch
                best_state = copy.deepcopy(layer.state_dict())
                stale_epochs = 0
            else:
                stale_epochs += 1
            if stale_epochs >= args.patience:
                break

        print(
            f"config={configuration_index}/{len(configurations)} "
            f"lr={configuration.learning_rate:g} "
            f"class_exp={configuration.class_weight_exponent:g} "
            f"expansion_weight={configuration.expansion_weight:g} "
            f"distill={configuration.distillation_weight:g} "
            f"best_top1={best_accuracy:.4%} ({best_correct}/{len(val_y)}) "
            f"epoch={best_epoch}"
        )
        report_rows.append(
            {
                **asdict(configuration),
                "best_epoch": best_epoch,
                "validation_correct": best_correct,
                "validation_images": len(val_y),
                "validation_top1": best_accuracy,
            }
        )
        if best_accuracy > global_best_accuracy:
            global_best_accuracy = best_accuracy
            global_best_state = best_state
            global_best_configuration = configuration
            global_best_epoch = best_epoch

    winner = YOLO(str(args.model), task="classify")
    winner_linear = winner.model.model[-1].linear
    winner_linear.load_state_dict(
        {key: value.detach().cpu() for key, value in global_best_state.items()}, strict=True
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    winner.save(str(args.output))
    report = {
        "model": str(args.model),
        "data": str(args.data),
        "train_images": len(train_y),
        "validation_images": len(val_y),
        "weighted_expansion_train_images": int(train_expansion.sum()),
        "focus_classes": args.focus_classes,
        "baseline_validation_top1": baseline_accuracy,
        "best_validation_top1": global_best_accuracy,
        "best_epoch": global_best_epoch,
        "best_configuration": (
            asdict(global_best_configuration) if global_best_configuration else None
        ),
        "results": report_rows,
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved candidate: {args.output}")
    print(f"Saved report: {args.output.with_suffix('.json')}")


if __name__ == "__main__":
    main()
