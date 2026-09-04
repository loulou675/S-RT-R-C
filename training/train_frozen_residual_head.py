#!/usr/bin/env python3
"""Train a small nonlinear correction on top of frozen active YOLO features."""

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
    def __init__(self, samples: list[tuple[Path, int]]) -> None:
        self.samples = samples
        self.transform = classify_transforms(224)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        path, label = self.samples[index]
        with Image.open(path) as image:
            tensor = self.transform(image.convert("RGB"))
        return tensor, label


class ResidualHead(nn.Module):
    def __init__(
        self,
        anchor_weight: torch.Tensor,
        anchor_bias: torch.Tensor,
        hidden: int,
        dropout: float,
    ) -> None:
        super().__init__()
        self.register_buffer("anchor_weight", anchor_weight.detach().clone())
        self.register_buffer("anchor_bias", anchor_bias.detach().clone())
        self.normalization = nn.LayerNorm(anchor_weight.shape[1])
        self.input = nn.Linear(anchor_weight.shape[1], hidden)
        self.activation = nn.GELU()
        self.dropout = nn.Dropout(dropout)
        self.output = nn.Linear(hidden, anchor_weight.shape[0])
        nn.init.zeros_(self.output.weight)
        nn.init.zeros_(self.output.bias)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        anchor = F.linear(features, self.anchor_weight, self.anchor_bias)
        residual = self.output(
            self.dropout(self.activation(self.input(self.normalization(features))))
        )
        return anchor + residual


@dataclass(frozen=True)
class Configuration:
    hidden: int
    learning_rate: float
    weight_decay: float
    distillation_weight: float


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


def extract_features(
    network: nn.Module,
    linear: nn.Linear,
    samples: list[tuple[Path, int]],
    device: str,
    batch_size: int,
):
    loader = DataLoader(
        ImageDataset(samples), batch_size=batch_size, shuffle=False, num_workers=0
    )
    feature_batches = []
    label_batches = []
    captured: list[torch.Tensor] = []

    def capture(_module, inputs) -> None:
        captured.append(inputs[0].detach())

    hook = linear.register_forward_pre_hook(capture)
    network.eval()
    with torch.inference_mode():
        for images, labels in loader:
            captured.clear()
            network(images.to(device))
            if len(captured) != 1:
                raise RuntimeError("Expected one classifier feature capture")
            feature_batches.append(captured[0].float().cpu())
            label_batches.append(labels.long())
    hook.remove()
    return torch.cat(feature_batches), torch.cat(label_batches)


def accuracy(head: nn.Module, features: torch.Tensor, labels: torch.Tensor):
    head.eval()
    with torch.inference_mode():
        predicted = head(features).argmax(1)
    correct = int((predicted == labels).sum())
    return correct, correct / len(labels)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--feature-batch", type=int, default=128)
    parser.add_argument("--train-batch", type=int, default=512)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--patience", type=int, default=35)
    parser.add_argument("--hidden-sizes", type=int, nargs="+", default=[32, 64, 128])
    parser.add_argument("--learning-rates", type=float, nargs="+", default=[1e-4, 3e-4])
    parser.add_argument("--weight-decays", type=float, nargs="+", default=[1e-4])
    parser.add_argument("--distillation-weights", type=float, nargs="+", default=[0.4, 0.7])
    parser.add_argument("--dropout", type=float, default=0.15)
    args = parser.parse_args()

    torch.manual_seed(42)
    random.seed(42)
    model = YOLO(str(args.model), task="classify")
    names = [model.names[index] for index in range(len(model.names))]
    class_index = {name: index for index, name in enumerate(names)}
    train_samples = samples_for_split(args.data.resolve(), "train", class_index)
    validation_samples = samples_for_split(args.data.resolve(), "val", class_index)
    network = model.model.to(args.device).eval()
    source_linear = network.model[-1].linear
    train_x, train_y = extract_features(
        network, source_linear, train_samples, args.device, args.feature_batch
    )
    val_x, val_y = extract_features(
        network, source_linear, validation_samples, args.device, args.feature_batch
    )
    train_x = train_x.to(args.device)
    train_y = train_y.to(args.device)
    val_x = val_x.to(args.device)
    val_y = val_y.to(args.device)
    anchor_weight = source_linear.weight.detach().float().to(args.device)
    anchor_bias = source_linear.bias.detach().float().to(args.device)
    with torch.inference_mode():
        anchor_train_logits = F.linear(train_x, anchor_weight, anchor_bias)
        anchor_val_logits = F.linear(val_x, anchor_weight, anchor_bias)
        baseline_correct = int((anchor_val_logits.argmax(1) == val_y).sum())
        baseline_accuracy = baseline_correct / len(val_y)
    print(
        f"baseline validation_top1={baseline_accuracy:.4%} "
        f"({baseline_correct}/{len(val_y)})",
        flush=True,
    )

    configurations = [
        Configuration(hidden, learning_rate, weight_decay, distillation_weight)
        for hidden in args.hidden_sizes
        for learning_rate in args.learning_rates
        for weight_decay in args.weight_decays
        for distillation_weight in args.distillation_weights
    ]
    rows = []
    global_best_accuracy = baseline_accuracy
    global_best_state = None
    global_best_configuration = None
    global_best_epoch = 0
    for index, configuration in enumerate(configurations, start=1):
        torch.manual_seed(42)
        generator = torch.Generator().manual_seed(42)
        head = ResidualHead(
            anchor_weight, anchor_bias, configuration.hidden, args.dropout
        ).to(args.device)
        optimizer = torch.optim.AdamW(
            head.parameters(),
            lr=configuration.learning_rate,
            weight_decay=configuration.weight_decay,
        )
        best_accuracy = baseline_accuracy
        best_correct = baseline_correct
        best_epoch = 0
        best_state = copy.deepcopy(head.state_dict())
        stale = 0
        for epoch in range(1, args.epochs + 1):
            permutation = torch.randperm(len(train_y), generator=generator).to(args.device)
            head.train()
            for start in range(0, len(train_y), args.train_batch):
                batch_indices = permutation[start : start + args.train_batch]
                logits = head(train_x[batch_indices])
                supervised = F.cross_entropy(logits, train_y[batch_indices])
                distillation = F.kl_div(
                    F.log_softmax(logits / 2.0, dim=1),
                    F.softmax(anchor_train_logits[batch_indices] / 2.0, dim=1),
                    reduction="batchmean",
                ) * 4.0
                loss = (
                    (1.0 - configuration.distillation_weight) * supervised
                    + configuration.distillation_weight * distillation
                )
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            correct, current_accuracy = accuracy(head, val_x, val_y)
            if current_accuracy > best_accuracy:
                best_accuracy = current_accuracy
                best_correct = correct
                best_epoch = epoch
                best_state = copy.deepcopy(head.state_dict())
                stale = 0
            else:
                stale += 1
            if stale >= args.patience:
                break
        print(
            f"config={index}/{len(configurations)} hidden={configuration.hidden} "
            f"lr={configuration.learning_rate:g} wd={configuration.weight_decay:g} "
            f"distill={configuration.distillation_weight:g} "
            f"best_top1={best_accuracy:.4%} ({best_correct}/{len(val_y)}) "
            f"epoch={best_epoch}",
            flush=True,
        )
        rows.append(
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

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "active_model": str(args.model),
            "configuration": (
                asdict(global_best_configuration) if global_best_configuration else None
            ),
            "state_dict": global_best_state,
            "class_names": names,
        },
        args.output,
    )
    report = {
        "model": str(args.model),
        "data": str(args.data),
        "train_images": len(train_y),
        "validation_images": len(val_y),
        "baseline_validation_top1": baseline_accuracy,
        "best_validation_top1": global_best_accuracy,
        "best_epoch": global_best_epoch,
        "best_configuration": (
            asdict(global_best_configuration) if global_best_configuration else None
        ),
        "results": rows,
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved residual candidate: {args.output}")
    print(f"Saved report: {args.output.with_suffix('.json')}")


if __name__ == "__main__":
    main()
