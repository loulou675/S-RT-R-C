# SỌRT RÁC ONNX model files

The browser uses the calibrated v71e four-model item-classifier ensemble:

- `waste_classifier_v71e_bottle_refined.onnx`
- `waste_classifier_v66_s_late.onnx`
- `waste_classifier_v66_s_frozen.onnx`
- `waste_classifier_v69_m_feedback.onnx`
- `waste_classifier_ensemble.json`
- `labels.json`

All four models expect a 224 x 224 RGB image. Their probabilities are
temperature-scaled and combined with class-wise weights and biases from the
runtime JSON by `src/providers/vision/calibratedEnsemble.ts`. The first ONNX
file is the v29 YOLO26n component; the other components are two YOLO26s models
and one YOLO26m model.

The deployed item ensemble is candidate v71e with 41 outputs, including
`disposable_cutlery` and `unknown`. It keeps the first three v66 components and
replaces the YOLO26m component with a validation-selected feedback refinement
for `plastic_takeaway_cup` and `printing_paper`, then conservatively refines
only the dominant YOLO26n classifier row for `plastic_water_bottle`. It has not
passed the production release gates. Previous browser bundles remain
recoverable from Git history and the local model archive.

On the unchanged 330-image held-out test set, v71e reaches 71.8% single-view
item top-1 accuracy (237/330), compared with v66's 71.5% (236/330). It fixes
one additional `plastic_takeaway_cup` image, has no correct-to-wrong held-out
class regression, preserves 85.2% unknown rejection recall, and keeps
hazardous-class macro recall at 70.2%. These figures are not production-ready;
see `training/candidate-v69-vs-v66-heldout.json`.

The separate `waste_bin_classifier.onnx` remains available for experiments but
is disabled by default because it was not part of the accepted v71e evaluation.
Set `VITE_BIN_MODEL_ENABLED=true` only when deliberately evaluating that hybrid.

When the exact v71e ensemble rejects an image, the app can lazily load the
separate `waste_material_classifier.onnx` seven-class broad-material model. It
does not replace or change accepted v71e predictions. Accepted material
predictions use the normal result sheet with explicit material-only caveats.
See `MATERIAL_MODEL_CARD.md` and
`training/material-fallback-v1-evaluation.json` for its data, thresholds,
held-out results, and limitations.

The original v66 bundle remains reproducible with
`training/export_v66_browser_ensemble.py`; the v71e deployment keeps v69's
fourth exported component and changes only the dominant component's
`plastic_water_bottle` classifier row plus the runtime version/path.
The app rejects any component whose output count differs from `labels.json`.
`disposable_cutlery` is now present at index 6 in every ensemble component.

Local development can use `VITE_USE_MOCK_VISION=true`, but mock mode is disabled by default.
