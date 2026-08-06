# Local YOLO26 training workspace

This directory is for training data and model preparation. It is intentionally separate from the Vite frontend so the browser app stays lightweight. Training images, experiment runs, and exported files are ignored by Git.

## Add images

Put one-item photos under the matching class folder:

```text
training/dataset/
├── train/
│   ├── plastic_water_bottle/
│   ├── aluminium_drink_can/
│   ├── plastic_takeaway_cup/
│   ├── fruit_peel/
│   ├── cardboard_box/
│   ├── paper_cup/
│   ├── battery/
│   └── unknown/
├── val/
└── test/
```

Use the same eight folder names in each split. Keep each image focused on one item, but vary the angle, distance, lighting, background, and amount of occlusion. Include representative non-target images in `unknown`.

## Curated single-item workflow

Before training, the local curation workflow can quarantine reviewed multi-item
or mismatched files without deleting them:

```bash
python training/curate_single_item_dataset.py
python training/collect_trashnet_single_items.py
python training/prepare_curated_splits.py
python training/augment_minority_classes.py
```

The trainer then uses `training/dataset_curated`. The supplemental TrashNet
images are used only where the source label is defensible: cardboard, metal
cans, and non-target examples under `unknown`. Plastic is not mapped broadly
because it cannot distinguish the app's bottle and takeaway-cup classes.

The recommended first split is approximately 70% training, 15% validation, and 15% test. Do not put near-duplicate photos in more than one split.

## Train outside the frontend dependencies

Install Ultralytics in a separate Python environment, not in the Vite app:

```bash
python -m pip install ultralytics
```

From the repository root, train a small classification model at the same input size expected by the browser integration:

```bash
yolo classify train \
  model=yolo26n-cls.pt \
  data="$(pwd)/training/dataset" \
  imgsz=224 \
  epochs=50 \
  project="$(pwd)/training/runs" \
  name=waste-classifier
```

Export the best checkpoint to ONNX:

```bash
yolo export \
  model="$(pwd)/training/runs/classify/waste-classifier/weights/best.pt" \
  format=onnx \
  imgsz=224 \
  project="$(pwd)/training/exports"
```

Before using the result in the browser, verify the exported model's class index order and create `public/models/labels.json` from that order. The example file already contains the eight app codes:

```text
public/models/labels.example.json
```

Copy the final model as:

```text
public/models/waste_classifier.onnx
```

The frontend will continue to use the existing rule engine after the model returns one of these item codes.

## Field-photo review batches

The local candidate collectors add real-world review images without retraining:

```bash
python training/collect_taco_crops.py
python training/collect_bdwaste_samples.py
python training/collect_hf_battery_samples.py
python training/ensure_app_compatible_images.py
```

TACO crops retain the original Flickr URL for each object. BDWaste is CC BY
4.0 and the battery supplement is recorded with its dataset license. Review
and remove unsuitable multi-item or mismatched candidates before running the
curated split/training workflow again. The compatibility pass accepts the
same JPEG/PNG/WebP formats as the frontend and quarantines other files under
`training/quarantine/incompatible-images/` instead of deleting them.
