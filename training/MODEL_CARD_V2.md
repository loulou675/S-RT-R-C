# SỌRT RÁC waste classifier v2

## Purpose

This is a browser-side, single-object image classifier for the six SỌRT RÁC
sorting categories. It predicts one of 32 item classes plus `unknown`; the app
then maps the item to a bin using curated disposal data.

The model is not an object detector. The user should place one item inside the
camera guide or upload an image in which one item is clearly dominant.

## Model and input

- Architecture: Ultralytics YOLO classification nano checkpoint
- Input: one centered RGB image, 224 x 224
- Normalization: RGB values scaled to 0-1
- Output: 33 class probabilities in the order stored in `public/models/labels.json`
- Browser runtime: ONNX Runtime Web

## Training run

- Run: `training/runs/waste-classifier-v2`
- Seed: 42
- Maximum epochs: 80; early stopping enabled
- Reviewed training set: 3,346 images
- Reviewed holdout: 157 images, 3-8 per class
- Sources and restrictions: see `training/DATA_SOURCES.md` and the JSONL manifests

## Holdout results

| Metric | v1 baseline | v2 |
| --- | ---: | ---: |
| Exact item top-1 accuracy | 55.4% | 56.7% |
| Exact item macro recall | 53.7% | 54.4% |
| Known-item bin accuracy | 65.1% | 69.8% |
| Known-bin macro recall | 65.5% | 70.6% |
| Hazardous-class macro recall | 63.3% | 63.4% |

These numbers are directional because the holdout has only 3-8 images per
class. They are not evidence of production readiness.

## Known weaknesses

- `aluminium_drink_can`, `drink_carton`, `tissue`, and `unknown` had zero exact
  recall on this small holdout.
- The model can put an item in the correct bin while naming the exact object
  incorrectly.
- Brands, crushed packaging, glare, clutter, and tiny objects remain difficult.
- An `unknown` training class cannot cover every object outside the supported
  list. Confidence rejection remains necessary.

The app currently accepts ordinary predictions at 0.55 confidence with a 0.15
top-two margin. Hazardous items require 0.80 confidence. Failed or uncertain
predictions should be corrected through the private feedback workflow, reviewed
by a person, and added only to a later training run.

## Release decision

V2 replaces V1 in `public/models/` because it improves the primary MVP outcome,
correct-bin accuracy, by 4.7 percentage points on the same reviewed holdout.
Continue to present results as guidance, not guaranteed material identification.
