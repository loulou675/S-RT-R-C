# Broad-material classifier v1

This browser model is a separate seven-class YOLO26n classifier. It runs only
after the active v69 exact-item ensemble returns `ITEM_NOT_RECOGNISED` or
`ITEM_AMBIGUOUS`. A sufficiently confident prediction opens the same full
result sheet as an exact-item result, with a visible **Material-based result**
label and material-specific caveats.

## Outputs

- `plastic`
- `metal`
- `paper_cardboard`
- `organic`
- `glass`
- `electronic_battery`
- `mixed_uncertain`

## Data and training

The model was fine-tuned for five epochs at 224 x 224 from the existing
YOLO26n bin-classifier checkpoint. Its data was derived from the preserved v66
41-item-class train, validation, and test splits by mapping each item class to
one broad material class. Only the training split was oversampled, to at least
800 files per material class; validation and test were left untouched. The
standalone validation top-1 score was 73.5% (373 images).

This is not an independently annotated material dataset. In particular,
composite objects and packaging can contain materials that are not visible in a
single image, and the glass class has only 92 distinct training images before
oversampling.

## Cascade calibration

Acceptance thresholds were chosen on the validation split only, using the v66
exact-item predecessor whose calibration is retained by v69. The selection
required at least 85% precision among accepted material results and at least
90% precision for accepted electronic/battery predictions, while maximizing
the number of correct results recovered after v66 rejected an image.

- Minimum material confidence: 0.95
- Minimum top-1 margin: 0.05
- Minimum electronic/battery confidence: 0.70
- Validation: 49/57 accepted material results correct (85.96% precision),
  covering 37.25% of v66-rejected images
- Untouched test: 46/54 accepted material results correct (85.19% precision),
  covering 40.91% of v66-rejected images
- Untouched test electronic/battery results: 2/2 correct

See `training/material-fallback-v1-evaluation.json` for the complete report and
confusion details. The evaluator reproduces the calibrated four-model item
ensemble and then scores this material model only on its rejected images.

## Limitations

Material appearance alone cannot reliably determine cleanliness, coatings,
hidden layers, chemical contamination, sharps, pressurisation, or local
acceptance rules. The app therefore gives cautious preparation instructions,
marks every such sheet as material-based, and withholds a material result when
the thresholds are not met. `mixed_uncertain` deliberately does not select a
disposal bin.

This model is suitable for controlled field testing, not a production release.
