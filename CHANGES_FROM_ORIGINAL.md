# Changes from the original repository

Baseline: remote `main` at commit `bd05d4f` (`Add GitHub Pages build`), whose history begins at `89d8c14` (`Initial commit`).

## Frontend and user flow

- Added a working local Vite workflow with a real browser-side ONNX vision provider.
- Added image validation, crop/resize/zoom editing, and preprocessing for uploaded or scanned images.
- Updated the sorting reference data, bin colors, labels, and Vietnamese/English item presentation.
- Added clearer confidence, margin, unknown-item, and hazardous-item handling.
- Added a Pages build helper and local environment example.

## Model and waste classes

- Added the eight-class YOLO26 classifier contract:
  `aluminium_drink_can`, `battery`, `cardboard_box`, `fruit_peel`,
  `paper_cup`, `plastic_takeaway_cup`, `plastic_water_bottle`, and `unknown`.
- Added the exported browser model at `public/models/waste_classifier.onnx` and matching `labels.json`.
- Added the local training/curation workflow, source/license logs, split preparation, conservative augmentation, and image-format validation.
- The current local model was trained from the curated dataset and verified with the frontend test/build checks.

## Project maintenance

- Removed unused frontend development dependencies from `package.json` and `pnpm-lock.yaml`.
- Added ignore rules for local datasets, model runs, quarantine files, caches, and environment files.
- Updated documentation and seed/reference data for the new workflow.
- Removed the obsolete test setup import that depended on a removed testing package.

Generated `node_modules/` and existing build artifacts were intentionally left in the repository; their deletion is not part of this update.
