# SỌRT RÁC ONNX model files

The browser uses the calibrated v66 four-model item-classifier ensemble:

- `waste_classifier.onnx`
- `waste_classifier_v66_s_late.onnx`
- `waste_classifier_v66_s_frozen.onnx`
- `waste_classifier_v66_m_frozen.onnx`
- `waste_classifier_ensemble.json`
- `labels.json`

All four models expect a 224 x 224 RGB image. Their probabilities are
temperature-scaled and combined with class-wise weights and biases from the
runtime JSON by `src/providers/vision/calibratedEnsemble.ts`. The first ONNX
file is the v29 YOLO26n component; the other components are two YOLO26s models
and one YOLO26m model.

The locally deployed item ensemble is candidate v66 with 41 outputs, including
`disposable_cutlery` and `unknown`. It was promoted for field testing on
2026-08-22 after preserving every v61 success on the original held-out set. It
has not passed the production release gates. The previous v61 browser bundle is
recoverable from Git history and from the local model archive used for this
release.

On the expanded untouched 330-image held-out test set, v66 reaches 71.5%
single-view item top-1 accuracy (236/330), including 1/4 disposable-cutlery
images. On the original 326-image v61 set it preserves the same 235 correct
predictions (72.1%), with no old-class regression. These figures are not
production-ready; see `training/candidate-v66-four-model-41class-heldout.json`.

The separate `waste_bin_classifier.onnx` remains available for experiments but
is disabled by default because it was not part of the accepted v66 evaluation.
Set `VITE_BIN_MODEL_ENABLED=true` only when deliberately evaluating that hybrid.

Use `training/export_v66_browser_ensemble.py` to reproduce the browser files.
The app rejects any component whose output count differs from `labels.json`.
`disposable_cutlery` is now present at index 6 in every ensemble component.

Local development can use `VITE_USE_MOCK_VISION=true`, but mock mode is disabled by default.
