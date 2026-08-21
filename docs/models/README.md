# SỌRT RÁC ONNX model files

The browser uses the calibrated v61 four-model item-classifier ensemble:

- `waste_classifier.onnx`
- `waste_classifier_v61_s_late.onnx`
- `waste_classifier_v61_s_frozen.onnx`
- `waste_classifier_v61_m_frozen.onnx`
- `waste_classifier_ensemble.json`
- `labels.json`

All four models expect a 224 x 224 RGB image. Their probabilities are
temperature-scaled and combined with class-wise weights and biases from the
runtime JSON by `src/providers/vision/calibratedEnsemble.ts`. The first ONNX
file is the v29 YOLO26n component; the other components are two YOLO26s models
and one YOLO26m model.

The locally deployed item ensemble is candidate v61 with 40 outputs, including
`unknown`, `hair_clip`, `hair_tie`, `pen_marker`, and `phone_case`. It was
promoted for field testing on 2026-08-21 after passing the project’s 70% held-out
top-1 candidate goal. It has not passed the production release gates. The
previous accepted model remains recoverable from Git history and its evaluation
is preserved at `training/previous-accepted-model-evaluation.json`.

On the untouched 326-image held-out test set, v61 reaches 72.1% single-view
item top-1 accuracy, 61.9% macro recall, 70.2% hazardous-class macro recall,
79.0% known-item bin accuracy and 85.2% unknown rejection recall. These figures
are not production-ready; see `training/candidate-v61-acceptance-comparison.json`.

The separate `waste_bin_classifier.onnx` remains available for experiments but
is disabled by default because it was not part of the accepted v61 evaluation.
Set `VITE_BIN_MODEL_ENABLED=true` only when deliberately evaluating that hybrid.

Use `training/export_v61_browser_ensemble.py` to reproduce the browser files.
The app rejects any component whose output count differs from `labels.json`.
`disposable_cutlery` is available in search and training taxonomy but is not a
v61 output; it needs a new calibrated candidate before browser recognition.

Local development can use `VITE_USE_MOCK_VISION=true`, but mock mode is disabled by default.
