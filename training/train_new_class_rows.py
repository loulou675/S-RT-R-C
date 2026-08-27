#!/usr/bin/env python3
"""Learn only newly added classifier rows while preserving all legacy logits."""

from __future__ import annotations

import argparse
import copy
import itertools
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
            return self.transform(image.convert("RGB")), label


@dataclass(frozen=True)
class Configuration:
    learning_rate: float
    class_weight_exponent: float
    new_class_multiplier: float
    feedback_weight: float
    weight_decay: float


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


def extract_features(network, linear, samples, device: str, batch_size: int):
    loader = DataLoader(ImageDataset(samples), batch_size=batch_size, shuffle=False)
    features, labels = [], []
    captured: list[torch.Tensor] = []

    def capture(_module, inputs) -> None:
        captured.append(inputs[0].detach())

    hook = linear.register_forward_pre_hook(capture)
    network.eval()
    with torch.inference_mode():
        for images, batch_labels in loader:
            captured.clear()
            network(images.to(device))
            if len(captured) != 1:
                raise RuntimeError("Expected one classifier feature capture")
            features.append(captured[0].float().cpu())
            labels.append(batch_labels.long())
    hook.remove()
    return torch.cat(features), torch.cat(labels)


def merged_logits(
    features: torch.Tensor,
    fixed_weight: torch.Tensor,
    fixed_bias: torch.Tensor,
    new_indices: torch.Tensor,
    new_weight: torch.Tensor,
    new_bias: torch.Tensor,
) -> torch.Tensor:
    logits = F.linear(features, fixed_weight, fixed_bias)
    replacement = F.linear(features, new_weight, new_bias)
    return logits.index_copy(1, new_indices, replacement)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--new-row-model", type=Path)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--new-classes", nargs="+", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--feature-batch", type=int, default=128)
    parser.add_argument("--train-batch", type=int, default=1024)
    parser.add_argument("--epochs", type=int, default=240)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--learning-rates", type=float, nargs="+", default=[1e-4, 3e-4, 1e-3])
    parser.add_argument("--class-weight-exponents", type=float, nargs="+", default=[0.0, 0.25, 0.5])
    parser.add_argument("--new-class-multipliers", type=float, nargs="+", default=[1.0, 2.0, 4.0])
    parser.add_argument(
        "--feedback-weights",
        type=float,
        nargs="+",
        default=[1.0],
        help="Per-sample weight for reviewed feedback images.",
    )
    parser.add_argument(
        "--max-validation-drop",
        type=int,
        default=0,
        help=(
            "Allow an exploratory row candidate to lose this many validation "
            "predictions. Keep zero for a directly deployable candidate; a non-zero "
            "candidate must be safety-interpolated before deployment."
        ),
    )
    parser.add_argument("--weight-decays", type=float, nargs="+", default=[0.0, 1e-4])
    args = parser.parse_args()

    torch.manual_seed(42)
    random.seed(42)
    model = YOLO(str(args.model), task="classify")
    names = [model.names[index] for index in range(len(model.names))]
    class_index = {name: index for index, name in enumerate(names)}
    unknown = sorted(set(args.new_classes) - set(class_index))
    if unknown:
        raise SystemExit(f"Unknown new classes: {unknown}")
    new_indices = torch.tensor(
        [class_index[name] for name in args.new_classes], dtype=torch.long
    )

    train_samples = samples_for_split(args.data.resolve(), "train", class_index)
    val_samples = samples_for_split(args.data.resolve(), "val", class_index)
    network = model.model.to(args.device).eval()
    linear = network.model[-1].linear
    train_x, train_y = extract_features(
        network, linear, train_samples, args.device, args.feature_batch
    )
    val_x, val_y = extract_features(
        network, linear, val_samples, args.device, args.feature_batch
    )
    train_x, train_y = train_x.to(args.device), train_y.to(args.device)
    val_x, val_y = val_x.to(args.device), val_y.to(args.device)
    feedback_indices = torch.tensor(
        [
            index
            for index, (path, _label) in enumerate(train_samples)
            if path.name.startswith(("feedback-", "feedback_"))
        ],
        dtype=torch.long,
        device=args.device,
    )
    fixed_weight = linear.weight.detach().float().to(args.device)
    fixed_bias = linear.bias.detach().float().to(args.device)
    new_indices = new_indices.to(args.device)

    initialization = model
    if args.new_row_model:
        initialization = YOLO(str(args.new_row_model), task="classify")
        initialization_names = [
            initialization.names[index] for index in range(len(initialization.names))
        ]
        if initialization_names != names:
            raise SystemExit("New-row model class order does not match the fixed model")
    initialization_linear = initialization.model.model[-1].linear
    initial_new_weight = initialization_linear.weight.detach()[new_indices.cpu()].float().to(args.device)
    initial_new_bias = initialization_linear.bias.detach()[new_indices.cpu()].float().to(args.device)

    with torch.inference_mode():
        baseline_logits = merged_logits(
            val_x,
            fixed_weight,
            fixed_bias,
            new_indices,
            initial_new_weight,
            initial_new_bias,
        )
        baseline_correct = int((baseline_logits.argmax(1) == val_y).sum())
        baseline_nll = float(F.cross_entropy(baseline_logits, val_y))
        baseline_feedback_correct = 0
        if len(feedback_indices):
            baseline_feedback_logits = merged_logits(
                train_x[feedback_indices],
                fixed_weight,
                fixed_bias,
                new_indices,
                initial_new_weight,
                initial_new_bias,
            )
            baseline_feedback_correct = int(
                (
                    baseline_feedback_logits.argmax(1)
                    == train_y[feedback_indices]
                ).sum()
            )
    print(
        f"baseline validation_top1={baseline_correct / len(val_y):.4%} "
        f"({baseline_correct}/{len(val_y)}) nll={baseline_nll:.6f} "
        f"feedback={baseline_feedback_correct}/{len(feedback_indices)}",
        flush=True,
    )

    class_counts = torch.bincount(train_y, minlength=len(names)).float()
    configurations = [
        Configuration(*values)
        for values in itertools.product(
            args.learning_rates,
            args.class_weight_exponents,
            args.new_class_multipliers,
            args.feedback_weights,
            args.weight_decays,
        )
    ]
    rows = []
    global_best_correct = baseline_correct
    global_best_nll = baseline_nll
    global_best_feedback_correct = baseline_feedback_correct
    global_best_state = (initial_new_weight.detach().cpu(), initial_new_bias.detach().cpu())
    global_best_configuration = None
    global_best_epoch = 0
    for configuration_index, configuration in enumerate(configurations, start=1):
        generator = torch.Generator().manual_seed(42)
        new_weight = nn.Parameter(initial_new_weight.detach().clone())
        new_bias = nn.Parameter(initial_new_bias.detach().clone())
        optimizer = torch.optim.AdamW(
            [new_weight, new_bias],
            lr=configuration.learning_rate,
            weight_decay=configuration.weight_decay,
        )
        class_weights = class_counts.clamp_min(1).pow(
            -configuration.class_weight_exponent
        )
        class_weights /= class_weights.mean()
        class_weights[new_indices] *= configuration.new_class_multiplier
        class_weights = class_weights.to(args.device)
        best_correct = baseline_correct
        best_nll = baseline_nll
        best_feedback_correct = baseline_feedback_correct
        best_state = (new_weight.detach().cpu(), new_bias.detach().cpu())
        best_epoch = 0
        stale = 0
        for epoch in range(1, args.epochs + 1):
            permutation = torch.randperm(len(train_y), generator=generator).to(args.device)
            for start in range(0, len(train_y), args.train_batch):
                indices = permutation[start : start + args.train_batch]
                logits = merged_logits(
                    train_x[indices],
                    fixed_weight,
                    fixed_bias,
                    new_indices,
                    new_weight,
                    new_bias,
                )
                sample_loss = F.cross_entropy(
                    logits,
                    train_y[indices],
                    weight=class_weights,
                    reduction="none",
                )
                feedback_mask = torch.isin(indices, feedback_indices)
                sample_weights = torch.where(
                    feedback_mask,
                    torch.tensor(configuration.feedback_weight, device=args.device),
                    torch.tensor(1.0, device=args.device),
                )
                loss = (sample_loss * sample_weights).sum() / sample_weights.sum()
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            with torch.inference_mode():
                validation_logits = merged_logits(
                    val_x,
                    fixed_weight,
                    fixed_bias,
                    new_indices,
                    new_weight,
                    new_bias,
                )
                predicted = validation_logits.argmax(1)
                correct = int((predicted == val_y).sum())
                nll = float(F.cross_entropy(validation_logits, val_y))
                feedback_correct = 0
                if len(feedback_indices):
                    feedback_logits = merged_logits(
                        train_x[feedback_indices],
                        fixed_weight,
                        fixed_bias,
                        new_indices,
                        new_weight,
                        new_bias,
                    )
                    feedback_correct = int(
                        (
                            feedback_logits.argmax(1)
                            == train_y[feedback_indices]
                        ).sum()
                    )
            current_key = (feedback_correct, correct, -nll)
            best_key = (best_feedback_correct, best_correct, -best_nll)
            if (
                correct >= baseline_correct - args.max_validation_drop
                and current_key > best_key
            ):
                best_correct = correct
                best_nll = nll
                best_feedback_correct = feedback_correct
                best_epoch = epoch
                best_state = (new_weight.detach().cpu(), new_bias.detach().cpu())
                stale = 0
            else:
                stale += 1
            if stale >= args.patience:
                break
        print(
            f"config={configuration_index}/{len(configurations)} "
            f"lr={configuration.learning_rate:g} class_exp={configuration.class_weight_exponent:g} "
            f"new_multiplier={configuration.new_class_multiplier:g} wd={configuration.weight_decay:g} "
            f"feedback_weight={configuration.feedback_weight:g} "
            f"best_top1={best_correct / len(val_y):.4%} ({best_correct}/{len(val_y)}) "
            f"nll={best_nll:.6f} feedback={best_feedback_correct}/{len(feedback_indices)} "
            f"epoch={best_epoch}",
            flush=True,
        )
        rows.append(
            {
                **asdict(configuration),
                "best_epoch": best_epoch,
                "validation_correct": best_correct,
                "validation_images": len(val_y),
                "validation_top1": best_correct / len(val_y),
                "validation_nll": best_nll,
                "feedback_correct": best_feedback_correct,
                "feedback_images": len(feedback_indices),
            }
        )
        candidate_key = (best_feedback_correct, best_correct, -best_nll)
        global_key = (
            global_best_feedback_correct,
            global_best_correct,
            -global_best_nll,
        )
        if (
            best_correct >= baseline_correct - args.max_validation_drop
            and candidate_key > global_key
        ):
            global_best_correct = best_correct
            global_best_nll = best_nll
            global_best_feedback_correct = best_feedback_correct
            global_best_state = best_state
            global_best_configuration = configuration
            global_best_epoch = best_epoch

    winner = YOLO(str(args.model), task="classify")
    winner_linear = winner.model.model[-1].linear
    with torch.no_grad():
        winner_linear.weight[new_indices.cpu()] = global_best_state[0]
        winner_linear.bias[new_indices.cpu()] = global_best_state[1]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    winner.save(str(args.output))
    report = {
        "fixed_model": str(args.model),
        "new_row_model": str(args.new_row_model) if args.new_row_model else None,
        "data": str(args.data),
        "new_classes": args.new_classes,
        "train_images": len(train_y),
        "validation_images": len(val_y),
        "baseline_validation_top1": baseline_correct / len(val_y),
        "baseline_validation_nll": baseline_nll,
        "baseline_feedback_correct": baseline_feedback_correct,
        "max_validation_drop": args.max_validation_drop,
        "best_validation_top1": global_best_correct / len(val_y),
        "best_validation_nll": global_best_nll,
        "best_feedback_correct": global_best_feedback_correct,
        "feedback_images": len(feedback_indices),
        "best_validation_correct": global_best_correct,
        "best_epoch": global_best_epoch,
        "best_configuration": asdict(global_best_configuration) if global_best_configuration else None,
        "results": rows,
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved candidate: {args.output}")
    print(f"Saved report: {args.output.with_suffix('.json')}")


if __name__ == "__main__":
    main()
