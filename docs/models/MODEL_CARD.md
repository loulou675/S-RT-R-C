# SỌRT RÁC waste classifier model card

## Summary

This browser model is a 36-class image classifier for a single waste item placed
inside the camera guide. It predicts an item class; the application then maps
that class to one of six disposal groups and applies the relevant preparation
rules.

This is an MVP checkpoint, not a production model. The app must keep its
confidence and prediction-margin checks enabled and show an uncertain result
instead of forcing every image into a bin.

## Model and input

- Architecture: Ultralytics YOLO26n classification checkpoint, fine-tuned for
  the project taxonomy.
- Browser format: ONNX, 36 outputs.
- Input: one RGB image, center-cropped and resized to 224 x 224.
- Output order: `labels.json` is the authoritative index-to-code mapping.
- Intended scene: one item occupying most of the center camera guide.

## Dataset

The training set combines reviewed samples from TrashNet, Wikimedia Commons,
Open Images V7 and project camera feedback listed in `training/DATA_SOURCES.md`.
Source metadata is stored in the JSONL manifests. The Open Images extension
adds balanced negative examples such as people, furniture, clothing, toys,
plants, animals, electronics, transport and signage to improve rejection of
objects outside the waste taxonomy.

The current curated split contains:

- 5,197 training images after train-only augmentation;
- 368 validation images;
- 323 test images;
- 36 classes, including `unknown`.

The latest real-camera import adds 32 independently reviewed photos of clean
and visibly dirty packaging, paper cups, bottles, bags, food trays and used
masks. Clean/dirty/used status is retained as manifest metadata; it is not a
separate classifier output.

Several classes still contain too few independent original photographs.
Augmentation improves robustness but does not replace new real images.

## Evaluation

Checkpoint evaluated on the untouched test split:

- top-1 accuracy: 67.2%;
- macro recall: 56.2%;
- hazardous-class macro recall: 60.7%;
- correct six-bin destination for known items: 72.3%;
- macro recall across the six known bins: 70.0%.

With the browser acceptance thresholds (confidence 0.55, prediction margin
0.15 and hazardous confidence 0.80), known-item coverage is 71.9%, accepted
item precision is 74.6%, accepted bin precision is 89.9%, and 92.1% of the
dedicated unknown test images are rejected. There are 17 confidently accepted
wrong-bin predictions in the current test split.

Per-bin top-1 recall is 80.0% for Bottle & Can, 86.8% for Organic, 57.6% for
Clean Plastic, 67.7% for Paper & Cardboard, 62.5% for Landfill and 65.6% for
Hazardous. Direct `unknown` top-1 recall is 88.6%; threshold rejection is higher
because uncertain non-unknown predictions are also withheld from the user.

Strong test classes include `battery`, `medicine_blister_pack` and
`plastic_water_bottle` at 100%, `dirty_plastic_bag` at 100%, and `food_waste`
at 81.5%. The weakest classes are `tissue` at 0%, `drink_carton` and
`plastic_takeaway_cup` at 16.7%, and several low-sample classes at 33.3%.
These values are based on small per-class test counts and therefore have wide
uncertainty.

## Safety and limitations

- Do not use the model to make safety-critical decisions.
- Hazardous predictions require a higher confidence threshold in the app.
- An uncertain prediction should ask the user to retake the image or search by
  item name.
- The model does not reliably infer whether an item is dirty, wet, empty or made
  from a hidden composite material. The result screen must ask for these
  conditions where disposal depends on them.
- Faces, hands, cluttered scenes and items outside the taxonomy are represented
  in the negative set, but rejection still needs real-device testing.
- Confirm the upstream checkpoint license is compatible with the intended
  distribution before public or commercial release.

## Release target

Do not mark a later checkpoint production-ready until it reaches at least 85%
macro top-1 accuracy, 80% recall for every ordinary class, 90% recall for every
hazardous class, and passes fresh phone and webcam testing on at least 30 images
per class.
