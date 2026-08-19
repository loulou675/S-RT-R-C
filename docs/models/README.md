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

The deployed item model has 36 outputs, including `unknown`. The training target
has 40 item classes, but a 40-class model must not replace the deployed model
until it passes the release gates.

On the current 350-image held-out test set, the accepted item/bin ensemble
reaches 76.9% destination-bin accuracy. Exact item recognition remains weaker
than destination-bin recognition; see the training evaluation files before
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
