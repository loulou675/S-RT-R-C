# SỌRT RÁC training workspace

This folder contains the class contract, data preparation utilities, source manifests and the browser-model training workflow.

Start with the detailed Vietnamese handoff guide in
[HUONG_DAN_TRAIN_AI.md](./HUONG_DAN_TRAIN_AI.md). The short path is:

User-correction review is documented in
[REVIEW_USER_FEEDBACK.md](./REVIEW_USER_FEEDBACK.md).

```bash
python training/curate_single_item_dataset.py
python training/prepare_curated_splits.py
python training/augment_minority_classes.py --target 60
python training/validate_dataset.py --data training/dataset_curated --minimum 300
python training/train_and_export.py --data training/dataset_curated --epochs 100 --batch 32
python training/evaluate_per_class.py
```

The dataset layout follows the Ultralytics image-classification contract:

```text
training/dataset/
├── train/<class_code>/
├── val/<class_code>/
└── test/<class_code>/
```

The canonical phase-one classes and their six disposal groups are in `training/classes.json`. Raw images, curated images, experiment runs and exports are intentionally ignored by Git. Source manifests remain tracked for review and licensing.

The deployed browser files are:

```text
public/models/waste_classifier.onnx
public/models/labels.json
```

Do not manually reorder `labels.json`. `training/train_and_export.py` generates it from the trained checkpoint so its indexes match the model output.
