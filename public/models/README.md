# SỌRT RÁC ONNX model files

The browser uses two classifiers together:

- `waste_classifier.onnx`
- `labels.json`
- `waste_bin_classifier.onnx`
- `bin_labels.json`

Both models expect a 224 x 224 RGB image. The item model identifies the object;
the bin model validates the destination category. Their probability outputs are
combined by `src/providers/vision/ensembleSelection.ts` before the final item is
selected.

The locally deployed item model is candidate v23 with 40 outputs, including
`unknown`, `hair_clip`, `hair_tie`, `pen_marker`, and `phone_case`. It was
promoted for field testing on 2026-08-20 despite not passing the production
release gates. The previous 36-class model is preserved under
`training/model_archive/original-active-36class-20260820/`.

On the 326-image held-out test set, v23 reaches 65.6% single-view item top-1
accuracy and 68.4% with its best evaluated test-time augmentation group. These
figures are not production-ready; see the training evaluation files before
making a broader accuracy claim.

The current direct-bin checkpoint was refreshed with reviewed real and public
images for clothing, stationery, phone chargers, hair accessories, cosmetic
sponges and similar broad waste items. The production ensemble gives the direct
bin model a validation-selected weight of 0.53. It reaches 76.9% on the core
holdout. On the small 33-image broad-item holdout, direct-bin accuracy improved
from 24.2% to 75.8%; ensemble accuracy improved from 9.1% to 42.4%. Treat the
broad-item figures as preliminary because the holdout is small.

Use `training/train_and_export.py` to generate a matched model/labels pair. The
app rejects a model whose output count differs from its labels file.

Local development can use `VITE_USE_MOCK_VISION=true`, but mock mode is disabled by default.
