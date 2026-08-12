# SỌRT RÁC component detector v1

## Scope

This is an experimental browser-side detector for visible bottle caps and
container lids. The main object classifier identifies the product body;
the component detector only decides whether a detachable closure is visible.
The app maps that closure to `plastic_cap` or `lid` based on the identified
item and keeps the body as the dominant sorting category.

Straws, paper sleeves and remaining liquid are still supplied by reviewed
sorting rules. They are not claimed as visually detected by this model.

## Training data

- Source: reviewed TACO bounding-box annotations
- Training boxes: 283 caps and lids
- Validation boxes: 39
- Independent test boxes: 19
- Architecture: YOLO26 nano detection model
- Browser input: 640 x 640 RGB, values scaled to 0-1
- Resize: letterbox/contain with neutral padding
- Output: post-NMS rows shaped `[1, N, 6]`

## Independent test result

- Precision: 0.956
- Recall: 0.316
- mAP50: 0.350 (rounded)
- mAP50-95: 0.219

The dominant object result no longer waits for this detector; component
details are added after the category result is already visible. Keeping the
640 px input protects small-closure accuracy without delaying the main result.

The model is deliberately used with a 0.50 confidence threshold. It will miss
some closures. A missed closure falls back to the rule database; a detected
closure appears as a separate part in the result UI.

An additional image-level smoke test containing negative images at this 0.50
threshold produced 71.4% precision and 35.7% recall. This second test is also
small, so both measurements should be treated as baseline evidence rather than
a production guarantee.

## Multi-part experiment

A second candidate was trained for `closure` and `straw` using 690 training
images, including close-up augmentations. On the untouched 35-image test set
it reached precision 0.221, recall 0.184 and mAP50 0.112. The straw class had
zero precision and recall. That candidate was rejected and is not installed.

The UI continues to show rule-backed straw separation for relevant products.
Installing visual straw detection requires substantially more real, reviewed
straw bounding boxes from the actual phone-camera setting.

## Limitations

- The test set is small and the metrics are directional.
- Tiny, occluded, transparent or unusually shaped closures may be missed.
- This model does not determine whether an item is clean, dirty or contains
  liquid.
- It detects closure geometry, not closure material. The displayed disposal
  destination is inferred from the identified item and sorting rules.
- Do not treat inferred component material as a chemical material analysis.
