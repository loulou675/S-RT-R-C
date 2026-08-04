# SỌRT RÁC ONNX model files

Place the trained browser-ready model here:

- `waste_classifier.onnx`
- `labels.json`

The application expects a 224 x 224 RGB classifier unless the provider is adjusted for model metadata.
The model output must map to the internal item codes used by the rule engine.

Local development can use `VITE_USE_MOCK_VISION=true`, but mock mode is disabled by default.
