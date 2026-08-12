# Training experiment - 2026-08-12

## Objective

Increase visual diversity without replacing the app models unless an untouched
test set confirms a real improvement. The object classifier remains a
single-dominant-item model. The component detector currently targets closures
and straws.

## Data added and reviewed

- Recyclable and Household Waste: 4,650 training images across household waste
  and negative/unknown scenes.
- Open Images household crops: 1,154 candidates; only light bulb, plastic bag,
  steel food can and tissue mappings are approved for classifier candidates.
- Open Images component data: 182 straw scenes across source-provided
  train/validation/test splits.
- PackWISE v2: 1,054 instance crops plus 156 plastic-lid component samples.
  Broad plastic-bottle, plastic-foil/bag and paper-bag mappings are excluded
  from exact-item training.
- TACO: additional labelled litter crops for damaged, dirty, outdoor and
  cluttered states.
- Wikimedia Commons: small manually reviewed batches for weak classes. The
  2026-08-12 can batch kept 13 of 34 candidates; the mask batch kept 1 of 12.

## Classifier result

Candidate: `training/runs/waste-classifier-v5/weights/best.pt`

| Metric | Installed v2 | Candidate v5 |
| --- | ---: | ---: |
| Exact-item top-1 | 56.7% | 59.9% |
| Exact-item macro recall | 54.4% | 57.9% |
| Hazardous macro recall | 63.4% | 65.5% |
| Known-item bin accuracy | 69.8% | 67.8% |
| Known-bin macro recall | 70.6% | 69.1% |

Decision: do not install. Exact naming improved, but the primary sorting metric
regressed. Drink carton and tissue still had zero exact recall on the small
locked holdout.

## Component result

Best broad candidate: `training/runs/component-parts-v5/weights/best.pt`

| Class | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| Closure | 45.1% | 47.7% | 39.0% | 28.9% |
| Straw | 31.1% | 30.2% | 29.7% | 12.9% |
| Combined | 38.1% | 39.0% | 34.3% | 20.9% |

A close-up candidate raised precision but reduced recall and did not improve the
combined untouched test. On the original closure-only test, the installed
closure model reached mAP50 28.2%; the two-class candidate reached 24.3%.

Decision: do not install. The next detector dataset should add whole-object
phone photos with labelled lids and straws, especially objects held in hand,
on tables, partially occluded and under dim or reflective lighting.
