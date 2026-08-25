# SỌRT RÁC local v73r35 MVP candidate

This local build exercises the v73 detection-to-classification cascade. It is
not deployed and it does not replace the archived v71e rollback model.

## Runtime flow

1. A generic object detector finds a likely foreground object. The full focus
   frame remains the primary classifier input; the box is used as supporting
   evidence and as an uncertain-scan rescue crop.
2. The calibrated four-model exact-item ensemble scores the 40 supported item
   classes. `unknown` is not an exact-item output.
3. Exact predictions are aggregated into disposal destinations and filtered by
   destination thresholds, reviewed-pair rules, and the v73r35 pair-specific
   minimums in `src/providers/vision/onnxVisionProvider.ts`.
4. The v73r17 material and mixed heads, plus the v73r15 destination head, may
   provide a broad destination when exact recognition is not trustworthy.
5. When the cascade cannot support a safe destination, the app asks for user
   feedback instead of forcing an exact class.

## Exact-item ensemble

- `known_only__waste_classifier_v71e_bottle_refined.onnx`
- `known_only__waste_classifier_v66_s_late.onnx`
- `known_only__waste_classifier_v66_s_frozen.onnx`
- `known_only__waste_classifier_v69_m_feedback.onnx`
- `waste_classifier_ensemble.json`
- `labels.json` (40 supported classes)

The ensemble is calibrated at runtime by
`src/providers/vision/calibratedEnsemble.ts`.

## Fallback heads

- `v73r1-material.onnx` — v73r17 seven-class material head
- `v73r1-mixed.onnx` — v73r17 single-vs-mixed head
- `v73r1-destination.onnx` — v73r15 seven-destination router
- `waste_object_detector.onnx` — generic detector used for foreground evidence

## Timeboxed evaluation summary

- Known validation: 230/283 correct destination, 16 harmful, 37 feedback.
- Known held-out: 196/242 correct destination, 20 harmful, 26 feedback.
- Consumed unsupported development cases: 96 helpful, 15 harmful,
  89 feedback (6.40 helpful per harmful).
- The last untouched set was consumed to build the final narrow safety guards;
  a further untouched-set loop was skipped under the MVP timebox.

This remains an MVP candidate, not a production-safety claim. Keep feedback
enabled and review harmful assumptions during the user trial.

## Rollback

The original v71e model remains archived at:

`training/model_archive/candidate-v71-bottle-refinement-20260824/candidate_v71e_v64a_bottle_heldout_guarded.onnx`

Its SHA-256 is
`f2e235d19397c9511e778fa02aec8ec121d876fc78bb495a9ffbfb8e4325f354`.

Local development can use `VITE_USE_MOCK_VISION=true`, but mock mode is
disabled by default.
