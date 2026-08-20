#!/usr/bin/env python3
"""Evaluate deterministic multi-view classification on a validation split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T
from ultralytics import YOLO

from train_frozen_residual_head import ResidualHead


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class MultiViewDataset(Dataset):
    def __init__(self, samples: list[tuple[Path, int]]) -> None:
        self.samples = samples
        self.resize_224 = T.Resize(224, antialias=True)
        self.resize_256 = T.Resize(256, antialias=True)
        self.center = T.CenterCrop(224)
        self.five = T.FiveCrop(224)
        self.square = T.Resize((224, 224), antialias=True)
        self.tensor = T.ToTensor()

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        path, label = self.samples[index]
        with Image.open(path) as opened:
            image = opened.convert("RGB")
            center = self.center(self.resize_224(image))
            crops = self.five(self.resize_256(image))
            square = self.square(image)
            contained = ImageOps.contain(
                image, (224, 224), Image.Resampling.BILINEAR
            )

            def letterbox(fill: tuple[int, int, int]):
                canvas = Image.new("RGB", (224, 224), fill)
                canvas.paste(
                    contained,
                    ((224 - contained.width) // 2, (224 - contained.height) // 2),
                )
                return canvas

            letterbox_gray = letterbox((114, 114, 114))
            views = [center, T.functional.hflip(center)]
            views.extend(crops)
            views.extend(T.functional.hflip(crop) for crop in crops)
            views.extend([square, T.functional.hflip(square)])
            views.extend(
                [
                    letterbox_gray,
                    T.functional.hflip(letterbox_gray),
                    letterbox((255, 255, 255)),
                    letterbox((0, 0, 0)),
                    center.rotate(
                        8, resample=Image.Resampling.BILINEAR, fillcolor=(114, 114, 114)
                    ),
                    center.rotate(
                        -8, resample=Image.Resampling.BILINEAR, fillcolor=(114, 114, 114)
                    ),
                ]
            )
            tensors = torch.stack([self.tensor(view) for view in views])
        return tensors, label


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--search-group-weights", action="store_true")
    parser.add_argument("--scores-output", type=Path, default=None)
    parser.add_argument("--residual-head", type=Path, default=None)
    args = parser.parse_args()

    model = YOLO(str(args.model), task="classify")
    if args.residual_head is not None:
        checkpoint = torch.load(args.residual_head, map_location="cpu", weights_only=False)
        configuration = checkpoint["configuration"]
        if configuration is None or checkpoint["state_dict"] is None:
            raise SystemExit("Residual checkpoint did not improve on the active baseline")
        source_linear = model.model.model[-1].linear
        residual = ResidualHead(
            source_linear.weight.detach().float(),
            source_linear.bias.detach().float(),
            configuration["hidden"],
            0.0,
        )
        residual.load_state_dict(checkpoint["state_dict"], strict=True)
        model.model.model[-1].linear = residual
    names = [model.names[index] for index in range(len(model.names))]
    class_index = {name: index for index, name in enumerate(names)}
    samples = []
    for class_dir in sorted(path for path in args.data.iterdir() if path.is_dir()):
        samples.extend(
            (path, class_index[class_dir.name])
            for path in sorted(class_dir.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    loader = DataLoader(MultiViewDataset(samples), batch_size=args.batch, num_workers=0)
    network = model.model.to(args.device).eval()
    probability_batches = []
    logit_batches = []
    label_batches = []
    with torch.inference_mode():
        for views, labels in loader:
            batch_size, view_count, channels, height, width = views.shape
            output = network(
                views.reshape(batch_size * view_count, channels, height, width).to(args.device)
            )
            if isinstance(output, tuple):
                probabilities, logits = output
            else:
                logits = output
                probabilities = logits.softmax(1)
            probability_batches.append(
                probabilities.reshape(batch_size, view_count, -1).float().cpu()
            )
            logit_batches.append(logits.reshape(batch_size, view_count, -1).float().cpu())
            label_batches.append(labels)
    probabilities = torch.cat(probability_batches)
    logits = torch.cat(logit_batches)
    labels = torch.cat(label_batches)
    if args.scores_output is not None:
        args.scores_output.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {"probabilities": probabilities, "logits": logits, "labels": labels},
            args.scores_output,
        )

    groups = {
        "center": [0],
        "center_flip": [0, 1],
        "five_crop": [2, 3, 4, 5, 6],
        "ten_crop": list(range(2, 12)),
        "center_plus_five": [0, 2, 3, 4, 5, 6],
        "center_plus_ten": list(range(12)),
        "square": [12],
        "square_flip": [12, 13],
        "center_square": [0, 1, 12, 13],
        "all_views": list(range(14)),
        "letterbox": [14, 15, 16, 17],
        "center_letterbox": [0, 1, 14, 15, 16, 17],
        "rotated_center": [0, 1, 18, 19],
        "extended_all": list(range(20)),
    }
    rows = []
    for group_name, indices in groups.items():
        for aggregation, values in (("probability", probabilities), ("logit", logits)):
            scores = values[:, indices].mean(1)
            predicted = scores.argmax(1)
            correct = int((predicted == labels).sum())
            row = {
                "group": group_name,
                "aggregation": aggregation,
                "views": indices,
                "correct": correct,
                "images": len(labels),
                "top1": correct / len(labels),
            }
            rows.append(row)
            print(
                f"{group_name:<18} {aggregation:<11} "
                f"top1={row['top1']:.4%} ({correct}/{len(labels)})"
            )
    best = max(rows, key=lambda row: row["top1"])
    weight_search = []
    best_weights = None
    if args.search_group_weights:
        center_scores = probabilities[:, 0:2].mean(1)
        crop_scores = probabilities[:, 2:12].mean(1)
        square_scores = probabilities[:, 12:14].mean(1)
        weight_values = [step / 4 for step in range(17)]
        for center_weight in weight_values:
            for crop_weight in weight_values:
                for square_weight in weight_values:
                    if center_weight + crop_weight + square_weight == 0:
                        continue
                    scores = (
                        center_weight * center_scores
                        + crop_weight * crop_scores
                        + square_weight * square_scores
                    )
                    correct = int((scores.argmax(1) == labels).sum())
                    weight_search.append(
                        {
                            "center_weight": center_weight,
                            "crop_weight": crop_weight,
                            "square_weight": square_weight,
                            "correct": correct,
                            "images": len(labels),
                            "top1": correct / len(labels),
                        }
                    )
        best_weights = max(
            weight_search,
            key=lambda row: (
                row["top1"],
                -(
                    abs(row["center_weight"] - 1)
                    + abs(row["crop_weight"] - 1)
                    + abs(row["square_weight"] - 1)
                ),
            ),
        )
        print(
            "best_group_weights "
            f"center={best_weights['center_weight']:g} "
            f"crop={best_weights['crop_weight']:g} "
            f"square={best_weights['square_weight']:g} "
            f"top1={best_weights['top1']:.4%} "
            f"({best_weights['correct']}/{best_weights['images']})"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "model": str(args.model),
                "data": str(args.data),
                "view_order": [
                    "center224",
                    "center224_hflip",
                    "fivecrop_top_left",
                    "fivecrop_top_right",
                    "fivecrop_bottom_left",
                    "fivecrop_bottom_right",
                    "fivecrop_center",
                    "fivecrop_top_left_hflip",
                    "fivecrop_top_right_hflip",
                    "fivecrop_bottom_left_hflip",
                    "fivecrop_bottom_right_hflip",
                    "fivecrop_center_hflip",
                    "square224",
                    "square224_hflip",
                    "letterbox_gray",
                    "letterbox_gray_hflip",
                    "letterbox_white",
                    "letterbox_black",
                    "center_rotate_plus_8",
                    "center_rotate_minus_8",
                ],
                "best": best,
                "best_group_weights": best_weights,
                "group_weight_search": weight_search,
                "results": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
