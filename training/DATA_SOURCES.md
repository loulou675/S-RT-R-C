# Training data sources

Only data with a traceable source and reuse terms should enter a training run.
The local image folders are ignored by Git; the JSONL manifests preserve the
source URL, local class and license for each downloaded candidate.

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

### Bower waste annotations

- Source: <https://huggingface.co/datasets/BowerApp/bower-waste-annotations>
- License: MIT
- Use: independent phone-camera validation only
- Limitation: the publisher describes this as a validation dataset. Do not mix
  it into training splits; use it to measure generalisation after training.

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
