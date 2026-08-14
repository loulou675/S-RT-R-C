# SORT RAC component detector v2

## Scope

This browser-side YOLO26 nano detector finds two visible component types:

- `closure`: bottle caps and container lids
- `food`: visible food, fruit or vegetables inside or beside packaging

The main classifier still identifies the whole item. The rule engine combines
that result with detected components, keeps the largest visible part as the
main category and shows separate disposal steps when relevant.

## Training data

- Closure source: reviewed TACO bounding-box annotations
- Food source: reviewed Open Images V7 bounding-box annotations
- Train: 1,378 images after train-only closure oversampling
- Train boxes: 1,132 closure and 1,310 food
- Validation: 92 untouched images, 39 closure and 183 food boxes
- Test: 78 untouched images, 19 closure and 177 food boxes
- Browser input: fixed 416 x 416 RGB tensor, values scaled to 0-1
- Output: rows shaped `[1, N, 6]`

## Independent test result

- Overall precision: 0.608
- Overall recall: 0.419
- Overall mAP50: 0.397
- Overall mAP50-95: 0.264
- Closure mAP50: 0.279
- Food mAP50: 0.516

The final checkpoint was fine-tuned at a low learning rate on a balanced train
split. Validation and test data were never duplicated.

## Limitations

- Food detection does not determine whether food is spoiled, dirty or safe.
- Tiny, occluded, transparent or unusually shaped closures may be missed.
- Closure accuracy is lower than the former closure-only model; more diverse
  phone-camera closure images are needed.
- A food box indicates visible organic material, not its exact recipe or
  chemical composition.
- Sorting destinations still come from reviewed rules, not image color alone.
