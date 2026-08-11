# SỌRT RÁC ONNX model files

The browser-ready model pair lives here:

- `waste_classifier.onnx`
- `labels.json`

The application expects a 224 x 224 RGB classifier unless the provider is adjusted for model metadata.
The model output must map to the internal item codes used by the rule engine.

The checked-in model uses the 33-output phase-one class list in `training/classes.json`, including `unknown`. It is an MVP checkpoint and must pass the release gates in the training guide before any production accuracy claim.

The current checkpoint reaches 58.2% item top-1 accuracy, 58.0% item macro
recall and 67.4% correct six-bin destination for known items on 153 untouched
test images. See `MODEL_CARD.md` for per-class weaknesses, provenance and
release limitations.

Use `training/train_and_export.py` to generate a matched model/labels pair. The app now rejects a pair whose output counts differ instead of silently assigning the wrong class names.

Local development can use `VITE_USE_MOCK_VISION=true`, but mock mode is disabled by default.
