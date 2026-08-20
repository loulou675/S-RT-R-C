#!/usr/bin/env python3
"""Fine-tune the active YOLO classification head without BN-statistics drift.

Only the final Classify module is trainable. Every batch-normalization layer is
held in evaluation mode, while an immutable copy of the active head supplies a
distillation target. Candidate selection uses the fixed validation split only.
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
from ultralytics.data.augment import classify_augmentations, classify_transforms


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


class CachedImageDataset(Dataset):
    def __init__(self, samples: list[tuple[Path, int]], transform) -> None:
        rows = []
        for path, label in samples:
            with Image.open(path) as image:
                tensor = transform(image.convert("RGB"))
            rows.append((tensor, label, path.name.startswith("expansion_")))
        self.tensors = torch.stack([row[0] for row in rows])
        self.labels = torch.tensor([row[1] for row in rows], dtype=torch.long)
        self.expansion = torch.tensor([row[2] for row in rows], dtype=torch.bool)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int):
        return self.tensors[index], self.labels[index], self.expansion[index]


class CachedSourceImageDataset(Dataset):
    """Keep decoded train images in RAM while applying a fresh transform each epoch."""

    def __init__(self, samples: list[tuple[Path, int]], transform) -> None:
        self.rows = []
        self.transform = transform
        for path, label in samples:
            with Image.open(path) as image:
                source = image.convert("RGB").copy()
            self.rows.append((source, label, path.name.startswith("expansion_")))

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        image, label, expansion = self.rows[index]
        return self.transform(image), label, expansion


@dataclass(frozen=True)
class Configuration:
    learning_rate: float
    class_weight_exponent: float
    expansion_weight: float
    distillation_weight: float


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


def keep_batch_norm_frozen(network: nn.Module) -> None:
    for module in network.modules():
        if isinstance(module, nn.modules.batchnorm._BatchNorm):
            module.eval()


def logits_from_anchor(output):
    return output[1] if isinstance(output, tuple) else output


def evaluate(network: nn.Module, head: nn.Module, loader: DataLoader, device: str):
    network.eval()
    head.train()  # Classify returns logits in train mode; its dropout is zero.
    keep_batch_norm_frozen(network)
    correct = 0
    total = 0
    with torch.inference_mode():
        for images, labels, _ in loader:
            logits = network(images.to(device))
            labels = labels.to(device)
            correct += int((logits.argmax(1) == labels).sum())
            total += len(labels)
    return correct, correct / total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--learning-rates", type=float, nargs="+", default=[1e-5, 3e-5])
    parser.add_argument("--class-weight-exponents", type=float, nargs="+", default=[0.0])
    parser.add_argument("--expansion-weights", type=float, nargs="+", default=[1.0, 2.0])
    parser.add_argument("--distillation-weights", type=float, nargs="+", default=[0.5, 0.8])
    parser.add_argument("--cache-validation", action="store_true")
    parser.add_argument("--cache-train-images", action="store_true")
    parser.add_argument(
        "--focus-classes",
        nargs="*",
        default=[],
        help="Only expansion images from these classes receive expansion weighting.",
    )
    args = parser.parse_args()

    torch.manual_seed(42)
    random.seed(42)
    base = YOLO(str(args.model), task="classify")
    names = [base.names[index] for index in range(len(base.names))]
    class_index = {name: index for index, name in enumerate(names)}
    train_samples = samples_for_split(args.data.resolve(), "train", class_index)
    validation_samples = samples_for_split(args.data.resolve(), "val", class_index)
    if not train_samples or not validation_samples:
        raise SystemExit("Training and validation splits must be non-empty")
    unknown_focus = sorted(set(args.focus_classes) - set(class_index))
    if unknown_focus:
        raise SystemExit(f"Unknown focus classes: {unknown_focus}")
    focus_indices = {
        class_index[class_name] for class_name in args.focus_classes
    }
    class_counts = torch.bincount(
        torch.tensor([label for _, label in train_samples]), minlength=len(names)
    ).float()

    validation_transform = classify_transforms(224)
    validation_dataset = (
        CachedImageDataset(validation_samples, validation_transform)
        if args.cache_validation
        else ImageDataset(validation_samples, validation_transform)
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=args.batch,
        shuffle=False,
        num_workers=0,
    )
    configurations = [
        Configuration(
            learning_rate,
            class_weight_exponent,
            expansion_weight,
            distillation_weight,
        )
        for learning_rate in args.learning_rates
        for class_weight_exponent in args.class_weight_exponents
        for expansion_weight in args.expansion_weights
        for distillation_weight in args.distillation_weights
    ]

    base_network = base.model.to(args.device)
    base_head = base_network.model[-1]
    baseline_correct, baseline_accuracy = evaluate(
        base_network, base_head, validation_loader, args.device
    )
    print(
        f"baseline validation_top1={baseline_accuracy:.4%} "
        f"({baseline_correct}/{len(validation_samples)})",
        flush=True,
    )

    report_rows = []
    global_best_accuracy = baseline_accuracy
    global_best_correct = baseline_correct
    global_best_epoch = 0
    global_best_configuration = None
    global_best_state = copy.deepcopy(base_network.state_dict())
    train_transform = classify_augmentations(
        224,
        scale=(0.72, 1.0),
        ratio=(0.8, 1.25),
        hflip=0.5,
        vflip=0.0,
        auto_augment=None,
        hsv_h=0.015,
        hsv_s=0.2,
        hsv_v=0.2,
        erasing=0.05,
    )
    train_dataset = (
        CachedSourceImageDataset(train_samples, train_transform)
        if args.cache_train_images
        else ImageDataset(train_samples, train_transform)
    )

    for configuration_index, configuration in enumerate(configurations, start=1):
        torch.manual_seed(42)
        random.seed(42)
        candidate = YOLO(str(args.model), task="classify")
        network = candidate.model.to(args.device)
        head = network.model[-1]
        for parameter in network.parameters():
            parameter.requires_grad_(False)
        for parameter in head.parameters():
            parameter.requires_grad_(True)

        anchor_head = copy.deepcopy(head).to(args.device).eval()
        for parameter in anchor_head.parameters():
            parameter.requires_grad_(False)

        captured: list[torch.Tensor] = []

        def capture_input(_module, inputs) -> None:
            captured.append(inputs[0].detach())

        hook = head.register_forward_pre_hook(capture_input)
        optimizer = torch.optim.AdamW(
            head.parameters(), lr=configuration.learning_rate, weight_decay=1e-5
        )
        class_weights = class_counts.clamp_min(1).pow(
            -configuration.class_weight_exponent
        )
        class_weights /= class_weights.mean()
        class_weights = class_weights.to(args.device)
        generator = torch.Generator().manual_seed(42)
        train_loader = DataLoader(
            train_dataset,
            batch_size=args.batch,
            shuffle=True,
            generator=generator,
            num_workers=0,
        )
        best_accuracy = baseline_accuracy
        best_correct = baseline_correct
        best_epoch = 0
        best_state = copy.deepcopy(network.state_dict())
        stale_epochs = 0

        for epoch in range(1, args.epochs + 1):
            network.eval()
            head.train()
            keep_batch_norm_frozen(network)
            for images, labels, expansion in train_loader:
                images = images.to(args.device)
                labels = labels.to(args.device)
                expansion = expansion.to(args.device)
                if focus_indices:
                    focus_mask = torch.zeros_like(expansion, dtype=torch.bool)
                    for focus_index in focus_indices:
                        focus_mask |= labels == focus_index
                    expansion &= focus_mask
                captured.clear()
                logits = network(images)
                if len(captured) != 1:
                    raise RuntimeError("Expected one input capture for the classification head")
                with torch.no_grad():
                    anchor_logits = logits_from_anchor(anchor_head(captured[0]))
                supervised = F.cross_entropy(logits, labels, reduction="none")
                expansion_weights = torch.where(
                    expansion,
                    torch.tensor(configuration.expansion_weight, device=args.device),
                    torch.tensor(1.0, device=args.device),
                )
                weights = class_weights[labels] * expansion_weights
                supervised = (supervised * weights).sum() / weights.sum()
                distillation = F.kl_div(
                    F.log_softmax(logits / 2.0, dim=1),
                    F.softmax(anchor_logits / 2.0, dim=1),
                    reduction="batchmean",
                ) * 4.0
                loss = (
                    (1.0 - configuration.distillation_weight) * supervised
                    + configuration.distillation_weight * distillation
                )
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            correct, accuracy = evaluate(network, head, validation_loader, args.device)
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_correct = correct
                best_epoch = epoch
                best_state = copy.deepcopy(network.state_dict())
                stale_epochs = 0
            else:
                stale_epochs += 1
            print(
                f"config={configuration_index}/{len(configurations)} epoch={epoch} "
                f"val_top1={accuracy:.4%} best={best_accuracy:.4%}",
                flush=True,
            )
            if stale_epochs >= args.patience:
                break

        hook.remove()
        report_rows.append(
            {
                **asdict(configuration),
                "best_epoch": best_epoch,
                "validation_correct": best_correct,
                "validation_images": len(validation_samples),
                "validation_top1": best_accuracy,
            }
        )
        if best_accuracy > global_best_accuracy:
            global_best_accuracy = best_accuracy
            global_best_correct = best_correct
            global_best_epoch = best_epoch
            global_best_configuration = configuration
            global_best_state = best_state

    winner = YOLO(str(args.model), task="classify")
    winner.model.load_state_dict(
        {key: value.detach().cpu() for key, value in global_best_state.items()}, strict=True
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    winner.save(str(args.output))
    report = {
        "model": str(args.model),
        "data": str(args.data),
        "train_images": len(train_samples),
        "validation_images": len(validation_samples),
        "focus_classes": args.focus_classes,
        "baseline_validation_top1": baseline_accuracy,
        "best_validation_top1": global_best_accuracy,
        "best_validation_correct": global_best_correct,
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
