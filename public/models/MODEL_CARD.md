# SỌRT RÁC waste classifier model card

## Summary

This browser model is a calibrated 40-class ensemble for a single waste item placed
inside the camera guide. It predicts an item class; the application then maps
that class to one of six disposal groups and applies the relevant preparation
rules.

This is an MVP checkpoint, not a production model. The app must keep its
confidence and prediction-margin checks enabled and show an uncertain result
instead of forcing every image into a bin.

## Model and input

- Architecture: four fine-tuned Ultralytics YOLO26 classifiers (one YOLO26n,
  two YOLO26s and one YOLO26m) with validation-fitted class-wise calibration.
- Browser format: four ONNX files, each with 40 outputs, plus a calibration JSON.
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

- 5,432 training images after train-only augmentation;
- 368 validation images;
- 326 test images;
- 40 classes, including `unknown`.

The latest real-camera import adds 32 independently reviewed photos of clean
and visibly dirty packaging, paper cups, bottles, bags, food trays and used
masks. Clean/dirty/used status is retained as manifest metadata; it is not a
separate classifier output.

Several classes still contain too few independent original photographs.
Augmentation improves robustness but does not replace new real images.

## Evaluation

Candidate v61 evaluated once on the untouched test split:

- single-view top-1 accuracy: 72.1% (235/326);
- macro recall: 61.9%;
- hazardous-class macro recall: 70.2%;
- correct six-bin destination for known items: 79.0%;
- grouped known-item bin accuracy: 79.8%;
- unknown rejection recall: 85.2%.

Per-bin recall is 85.0% for Bottle & Can, 94.7% for Organic, 61.8% for Clean
Plastic, 67.6% for Paper & Cardboard, 76.2% for Landfill and 71.9% for Hazardous.
The weakest test classes remain `hair_clip`, `pen_marker`, `phone_case`, and
`tissue` at 0%, with only one to three test images in each class.
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
