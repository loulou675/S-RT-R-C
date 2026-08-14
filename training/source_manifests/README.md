# Training data sources

Only data with a traceable source and reuse terms should enter a training run.
The JSONL manifests in this folder preserve the source URL, local class and
license. Keep this folder for traceability; it does not need routine review.

## Approved sources

### Wikimedia Commons

- Source: <https://commons.wikimedia.org/>
- License: recorded per image in `commons-training-sources.jsonl`
- Use: product-level classes and varied backgrounds
- Requirement: review every contact sheet before training and retain the
  author, file page, license name and license URL in the manifest.

### BDWaste

- Source: <https://doi.org/10.17632/96g5pgfnfw.1>
- License: CC BY 4.0
- Use: real indoor and outdoor waste photos, especially organic waste
- Requirement: credit the dataset authors. Large archive downloads can be
  resumed or sampled later; failed downloads must not create source records.

### TrashNet

- Source: <https://github.com/garythung/trashnet>
- License: MIT
- Use: simple-background single-item negatives, cardboard and reviewed cans
- Limitation: its broad material folders do not reliably separate every app
  class. Ambiguous plastic, glass, paper and metal examples must be reviewed.

### Waste Garbage Management Dataset

- Source: <https://huggingface.co/datasets/omasteam/waste-garbage-management-dataset>
- License: MIT, as declared by the dataset card
- Use: battery, biological, cardboard and glass review candidates
- Limitation: source labels are broad. Keep only examples that match the target
  app class; do not map broad paper, plastic or metal folders automatically.

### Drinking Waste Classification

- Source: <https://www.kaggle.com/datasets/arkadiyhacks/drinking-waste-classification>
- License: CC0, as declared by the dataset page
- Use: phone-camera aluminium-can candidates with YOLO boxes
- Limitation: the archive contains long sequences of the same physical cans.
  Sample sparsely, keep these images in training only, and do not use them to
  inflate validation or test scores.

### Recyclable and Household Waste Classification

- Source: <https://www.kaggle.com/datasets/alistairking/recyclable-and-household-waste-classification>
- License: MIT, as declared by the dataset page
- Use: balanced household-item coverage for cans, bottles, paper, cardboard,
  food waste, bags, food containers and styrofoam
- Limitation: default and real-world subsets share a strong source style. Files
  prefixed with `rhw_` are training-only; independent sources must provide the
  validation and test images.

### Bower waste annotations

- Source: <https://huggingface.co/datasets/BowerApp/bower-waste-annotations>
- License: MIT
- Use: independent phone-camera validation only
- Limitation: the publisher describes this as a validation dataset. Do not mix
  it into training splits; use it to measure generalisation after training.

### TACO

- Source: <https://github.com/pedropro/TACO>
- Use: labelled object crops from litter photographed on roads, grass, beaches
  and other cluttered outdoor scenes
- Requirement: keep the original Flickr page in `taco-field-sources.jsonl` and
  manually review every crop. TACO metadata and code do not replace the terms
  attached to each original photograph.

### PackWISE v2

- Source: <https://fordatis.fraunhofer.de/handle/fordatis/463.2>
- License: CC BY 4.0
- Use: difficult conveyor scenes with instance boxes and masks; reviewed crops
  for beverage cartons, blister packs, cans, tissue, foam and paper cups; lid
  boxes for the component detector
- Limitation: broad source categories such as `plastic-bottle` and
  `plastic-foil/bag` are not mapped to narrower app classes. PackWISE validation
  and test images remain outside classifier training.

### Open Images V7

- Source: <https://storage.googleapis.com/openimages/web/index.html>
- Use: independently split bounding boxes for straws and reviewed household
  objects
- Limitation: Open Images labels visible objects rather than disposal rules.
  Only mappings listed in `build_classifier_candidate_v3.py` passed the local
  contact-sheet review; broad Bottle, Milk and Snack mappings are excluded.
- Organic extension: `collect_openimages_organic.py` uses human-verified
  validation bounding boxes for visible food, fruit and vegetables. It creates
  balanced classifier crops and collapses the same boxes to the component class
  `food`; source records are kept in `openimages-organic-sources.jsonl`.

## Excluded source

`TrashBox` remains excluded because its upstream repository does not provide
an explicit dataset license. Its collector is retained for reference but its
images must not be used in a published model until permission is confirmed.

## Review contract

1. One target object should dominate the image.
2. Remove watermarked, illustrated, damaged or unrelated files.
3. Keep difficult but correct backgrounds; do not keep label noise for the sake
   of reaching a target count.
4. Put unrelated objects, empty frames, hands and ordinary household items in
   `unknown` instead of forcing them into a waste class.
5. Never split visually identical items by brand or product flavour.
6. Never use validation or test images for augmentation.
