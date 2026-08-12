# Training the SỌRT RÁC vision model

## What the app expects

The app uses a **single-item image classifier**. The user places one object inside the square camera guide. The browser automatically captures only that square, resizes it to 224 x 224, converts RGB values to 0-1 floats, and sends a `[1, 3, 224, 224]` tensor to ONNX Runtime.

The current phase-one model contract contains 32 waste-object classes plus `unknown`, defined in `training/classes.json`. Searchable reference data can contain more items than the model: only visually distinct, well-supported classes should be trained.

## 1. Freeze the class list

Review `training/classes.json` with the team before collecting images. Do not rename a folder after data collection starts. Do not create separate image classes for clean/dirty, wet/dry, or empty/full; those conditions are sorting rules, not stable visual identities.

Run:

```bash
python training/sync_class_folders.py
```

This creates the required `train`, `val`, and `test` folder for every class.

## 2. Collect representative images

For a reliable first release, aim for at least **300 reviewed images per class**; 800-1,500 per class is a better target for classes with varied packaging. `unknown` should be at least as large and diverse as the largest target class.

Each target-class image should:

- contain exactly one labelled item;
- show the whole item, not a tiny object in a wide scene;
- let the item occupy roughly 55-85% of the square;
- include real phones, laptop webcams, tables, floors, hands, shadows, blur, rotation, crushed items, labels and different brands;
- include the same backgrounds and lighting users will encounter;
- be assigned by what is visibly present, not by filename or intended disposal bin.

The `unknown` class should include empty camera frames, faces, hands without waste, multiple-item scenes, clutter, objects outside the supported list, pets, furniture and confusing near-matches. This prevents the model from confidently guessing a bin for everything.

Do not copy nearly identical burst photos across splits. Keep photos of the same physical object or video session in one split only.

Recommended split:

- 70% train
- 15% validation
- 15% untouched test

## 3. Validate before training

```bash
python training/validate_dataset.py --minimum 300
```

This reports missing classes, low counts and exact duplicate leakage between splits. Fix every `CHECK` before training.

## 4. Train and export

Create a clean Python environment and install Ultralytics plus ONNX export support:

```bash
python -m pip install -U ultralytics onnx onnxslim
```

Then run a named candidate training job:

```bash
python training/train_and_export.py --epochs 100 --batch 32 --name waste-classifier-candidate
```

On Apple Silicon, add `--device mps`. On a CUDA machine or Google Colab GPU, add `--device 0`. If memory is insufficient, reduce `--batch` to 16 or 8.

The script trains at 224 x 224, evaluates the untouched test split, exports ONNX, and verifies class order. It keeps the candidate inside its run folder so the live app is not changed before evaluation.

After the candidate passes review, copy its `best.onnx` and generated `labels.json` into:

```text
public/models/waste_classifier.onnx
public/models/labels.json
```

Alternatively, include `--install` in a new training run to install that run automatically after it completes. Never edit label indexes by hand. Their order must exactly match the model output.

## 5. Acceptance test

Do not approve a model from overall accuracy alone. Review the confusion matrix and per-class recall. For hazardous classes, false negatives matter most. Test at least 30 new camera images per class through the actual web interface, not images seen during training.

Suggested release gates:

- at least 85% macro top-1 accuracy on the untouched test set;
- at least 80% recall for every ordinary class;
- at least 90% recall for hazardous classes;
- unknown and low-confidence images do not produce a disposal result;
- the same item works across at least three backgrounds and three lighting conditions.

If two classes repeatedly confuse each other, first inspect labels and collect harder examples. Merge visually indistinguishable classes when they have the same disposal rule. Lowering the confidence threshold should be the last option because it increases confident wrong answers.

## 6. Publish safely

Keep these production values:

```text
VITE_USE_MOCK_VISION=false
VITE_AI_NORMALIZATION=zero-one
VITE_AI_MIN_ACCEPTANCE=0.55
VITE_AI_MIN_MARGIN=0.15
VITE_AI_SPECIAL_HANDLING_MIN_ACCEPTANCE=0.8
```

Build the app again after replacing the model. For GitHub Pages, commit the rebuilt `docs` folder together with the new model and labels. Test in a private window to avoid a cached old model.

## When classification is no longer enough

This classifier is correct for the current one-object-in-a-square interaction. If the product later needs to find several objects anywhere in a camera scene, train an object-detection model with bounding boxes instead of expanding this classifier.

## Component detection

The result UI and rule engine can also accept detected parts. The supported
part codes are stored in `training/component_classes.json`. The first installed
model is intentionally narrow: the object classifier supplies the dominant
body and the detector looks only for detachable closures. This performs better
than asking a small detector to relearn the whole object from limited data.

To build a closure-and-straw candidate from the reviewed public boxes, run:

```text
python training/build_component_dataset.py --output training/component_dataset_parts --negative-images 80
python training/augment_component_crops.py --dataset training/component_dataset_parts --scale 3.2 --splits train
python training/train_component_detector.py --data training/component_dataset_parts/data.yaml --epochs 45 --batch 32 --imgsz 416 --export-imgsz 416
```

For later versions, annotate each visible part with a bounding box and keep all
parts from one photo in the same train, validation, or test split. Add a class
only after it has enough reviewed boxes and an independent test set. Remaining
liquid is a state, not a reliable bounding-box class, so keep it in sorting
rules or train a separate state classifier.

Export a detection ONNX model whose post-NMS output is shaped `[1, N, 6]`, with
each row containing `[x1, y1, x2, y2, confidence, class_index]` in the exported
image coordinates. Place the model and labels in `public/models/`, then set:

```text
VITE_COMPONENT_MODEL_PATH=/models/waste_components.onnx
VITE_COMPONENT_LABELS_PATH=/models/component_labels.json
VITE_COMPONENT_INPUT_SIZE=640
VITE_COMPONENT_MIN_ACCEPTANCE=0.50
```

Without these variables, the app uses the reviewed component breakdown stored
in the disposal rules. The object classifier supplies the dominant body and
main bin immediately. The component detector runs afterwards and enriches the
part guidance without delaying the main result.

The August 2026 two-class experiment for closure and straw was rejected:
precision 0.221, recall 0.184 and mAP50 0.112 on the untouched test set. Straw
precision and recall were both zero. Do not install that candidate. Collect at
least 300 diverse, reviewed real-camera straw boxes before trying that class
again; synthetic close-up crops alone were not sufficient.
