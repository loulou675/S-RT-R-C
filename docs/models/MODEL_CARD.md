# SỌRT RÁC waste classifier model card

## Summary

This browser model is a 33-class image classifier for a single waste item placed
inside the camera guide. It predicts an item class; the application then maps
that class to one of six disposal groups and applies the relevant preparation
rules.

This is an MVP checkpoint, not a production model. The app must keep its
confidence and prediction-margin checks enabled and show an uncertain result
instead of forcing every image into a bin.

## Model and input

- Architecture: Ultralytics YOLO26n classification checkpoint, fine-tuned for
  the project taxonomy.
- Browser format: ONNX, 33 outputs.
- Input: one RGB image, center-cropped and resized to 224 x 224.
- Output order: `labels.json` is the authoritative index-to-code mapping.
- Intended scene: one item occupying most of the center camera guide.

## Dataset

The training set combines reviewed samples from TrashNet, Wikimedia Commons and
the project manifests listed in `training/DATA_SOURCES.md`. Wikimedia files are
accepted only when their metadata reports CC0, CC BY, CC BY-SA, public-domain or
equivalent reuse terms. Source URL, author and license metadata are stored in
the JSONL manifests.

The current curated split contains:

- 1,980 training images after train-only augmentation;
- 153 validation images;
- 153 untouched test images;
- 33 classes, including `unknown`.

Several classes still contain too few independent original photographs.
Augmentation improves robustness but does not replace new real images.

## Evaluation

Checkpoint evaluated on the untouched test split:

- top-1 accuracy: 58.2%;
- top-5 accuracy: 85.0%;
- macro recall: 58.0%;
- hazardous-class macro recall: 59.1%.
- correct six-bin destination for known items: 67.4%;
- macro recall across the six bins: 67.7%.

Per-bin recall was 78.3% for Clean Plastic, 73.3% for Organic, 67.6% for
Hazardous, 64.0% for Paper & Cardboard, 61.9% for Bottle & Can, and 60.9% for
Landfill. The `unknown` recall was 22.2%, so rejecting uncertain predictions is
still essential.

Strong test classes included `plastic_bag` and `plastic_food_container` at
100%, `glass_drink_bottle` at 87.5%, and `food_waste` at 85.7%. These values are
based on small per-class test counts and therefore have wide uncertainty.

The weakest classes were `steel_food_can` and `tissue` at 0%, `unknown` at
22.2%, and `light_bulb`, `newspaper`, and `styrofoam_container` at 33.3%.
These classes require more independent, correctly labelled camera-like images
before release.

## Safety and limitations

- Do not use the model to make safety-critical decisions.
- Hazardous predictions require a higher confidence threshold in the app.
- An uncertain prediction should ask the user to retake the image or search by
  item name.
- The model does not reliably infer whether an item is dirty, wet, empty or made
  from a hidden composite material. The result screen must ask for these
  conditions where disposal depends on them.
- Faces, hands, cluttered scenes and items outside the taxonomy should be
  rejected, but the current `unknown` performance is not yet sufficient.
- Confirm the upstream checkpoint license is compatible with the intended
  distribution before public or commercial release.

## Release target

Do not mark a later checkpoint production-ready until it reaches at least 85%
macro top-1 accuracy, 80% recall for every ordinary class, 90% recall for every
hazardous class, and passes fresh phone and webcam testing on at least 30 images
per class.
