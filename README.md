# SỌRT RÁC

SỌRT RÁC is an MVP web application for an AI-powered waste sorting assistant at a configurable waste station.

The main recognition experience runs on one page: camera, upload, preview, processing and the sliding result panel all stay inside `/`.

The repository contains the complete application and AI integration layer, but an accurate custom waste classifier requires a trained ONNX model and a dataset representative of the intended real-world environment.

## Architecture

- React, TypeScript, Vite and React Router provide the multi-route web app.
- Browser MediaDevices handles laptop and mobile camera capture after explicit user action.
- Browser Canvas automatically extracts the centered camera guide, resizes it and prepares the RGB tensor.
- ONNX Runtime Web loads the calibrated v61 four-model ensemble from `/public/models/` for local browser inference.
- A `VisionProvider` interface separates the model from the app flow.
- Supabase Postgres stores normalized reference data, rules, condition questions, reuse suggestions and anonymous scan events.
- A short post-scan survey stores usability feedback locally first, then syncs it to Supabase when configured.
- The deterministic TypeScript rule engine selects active verified rules and never invents disposal guidance.
- Zod validates model labels and model output structure.
- Vitest covers rule/search behavior. Playwright covers critical browser flows in mock mode.

## Project Structure

```text
src/
  app/
  components/
  data/
  features/
    camera/
    search/
    sorting/
  lib/
    image-processing/
    supabase/
    validation/
  providers/
    vision/
  routes/
  services/
  test/
  types/
supabase/
  migrations/
  seed.sql
public/
  models/
tests/
  e2e/
```

## Setup

Install dependencies:

```bash
pnpm install
```

Use Node.js 22 or newer. Dependencies and generated `dist/` files are intentionally not committed.

Copy environment variables:

```bash
cp .env.example .env.local
```

Run locally:

```bash
pnpm dev
```

Do not open the source `index.html` directly from Finder. This is a React/Vite app and must be served by the local development server. For a quick mock-mode preview on this Mac, double-click `OPEN_SOT_RAC.command`.

Build:

```bash
pnpm build
```

To refresh the GitHub Pages copy in `docs/`:

```bash
pnpm build:pages
```

## Environment Variables

```text
VITE_SUPABASE_URL=https://mbgiaevxiabtdweydgwm.supabase.co
VITE_SUPABASE_ANON_KEY=
VITE_USE_MOCK_VISION=false
VITE_AI_ENSEMBLE_ENABLED=true
VITE_AI_ENSEMBLE_CONFIG_PATH=/models/waste_classifier_ensemble.json
VITE_AI_MODEL_PATH=/models/waste_classifier.onnx
VITE_AI_LABELS_PATH=/models/labels.json
VITE_AI_NORMALIZATION=zero-one
VITE_AI_MIN_ACCEPTANCE=0.55
VITE_AI_MIN_MARGIN=0.15
VITE_AI_SPECIAL_HANDLING_MIN_ACCEPTANCE=0.8
VITE_AI_TIMEOUT_MS=60000
VITE_BIN_MODEL_ENABLED=false
VITE_BIN_MODEL_PATH=/models/waste_bin_classifier.onnx
VITE_BIN_LABELS_PATH=/models/bin_labels.json
VITE_BIN_ENSEMBLE_WEIGHT=0.53
VITE_TRAINING_MODE=false
VITE_RESULT_FEEDBACK=true
VITE_FEEDBACK_AUTO_UPLOAD=true
```

Do not expose Supabase service-role keys in the browser.

## Private training mode

The correction prompt is controlled with `VITE_RESULT_FEEDBACK=true`. A user
must choose the correct item and consent before anything is sent. When Supabase
and `VITE_FEEDBACK_AUTO_UPLOAD=true` are configured, the app uploads the cropped
JPEG and correction to a private review queue automatically. Failed uploads
stay in a local outbox and retry at startup or when the browser comes back
online. There is no manual reviewer-export control in the deployed interface.

After field testing, set `VITE_RESULT_FEEDBACK=false` and rebuild the app to
remove the correction prompt. Vite environment variables are embedded at build
time, so changing the value requires a new deployment.

To publish a temporary training-mode Pages build, run:

```bash
pnpm build:pages:training
```

To restore the client-facing Pages build, run `pnpm build:pages` and push the
new `docs/` output.

## Supabase Setup

For the automatic result-feedback queue only, run
`supabase/migrations/002_training_feedback.sql` in the Supabase SQL Editor. It
is self-contained and can be run without loading the reference-data seed.

The same queue stores both kinds of result feedback. When
`predicted_item_code` equals `corrected_item_code`, the user confirmed that the
AI result was correct. When the values differ, the user selected a correction.
Every row remains `pending` until a reviewer accepts, relabels, or rejects it.

For post-scan survey responses, also run
`supabase/migrations/004_user_surveys.sql` once in the Supabase SQL Editor. The
answers are kept in a small browser outbox first, then inserted into the
`user_surveys` table automatically when Supabase is configured or the browser
comes back online. Survey responses never contain the uploaded image.

For the complete optional remote reference database, create a Supabase project,
then apply:

```bash
supabase db push
supabase db reset
```

The migration creates:

- `site_profiles`
- `bins`
- `materials`
- `waste_items`
- `item_aliases`
- `disposal_rules`
- `condition_questions`
- `reuse_suggestions`
- `scan_events`
- `training_feedback`
- `user_surveys`
- private Storage bucket `training-feedback`

Row Level Security is enabled. Anonymous users can read active reference data,
insert scan events, and submit consented pending corrections. They cannot read
the feedback queue or its private images and cannot modify reference tables.

Feedback images are center-cropped to 640 x 640 JPEG in the browser, which also
removes original image metadata. The database stores only the private image
path, labels, optional note, consent version and review state.

## ONNX Model

Place files in `public/models/`:

```text
public/models/waste_classifier.onnx
public/models/waste_classifier_v61_s_late.onnx
public/models/waste_classifier_v61_s_frozen.onnx
public/models/waste_classifier_v61_m_frozen.onnx
public/models/waste_classifier_ensemble.json
public/models/labels.json
```

The app expects a 224 x 224 RGB classifier unless the provider is adjusted for model metadata.

Example labels format:

```json
{
  "labels": [
    { "index": 0, "code": "plastic_water_bottle" },
    { "index": 1, "code": "aluminium_drink_can" },
    { "index": 2, "code": "plastic_takeaway_cup" },
    { "index": 3, "code": "unknown" }
  ]
}
```

The checked-in v61 ensemble and `labels.json` contain 40 visual classes,
including `unknown`. Searchable waste names
can be more detailed than model classes; disposal conditions such as clean,
dirty, wet or full are handled by rules after recognition.

No confidence score appears in the user interface. Scores are used only internally to reject uncertain results.

## Mock Mode

Mock mode is for development only:

```text
VITE_USE_MOCK_VISION=true
```

When enabled, the scan page shows `Development Mock Mode` and lets a developer choose a sample item before processing a still image.

Mock mode is disabled by default. If the production model is missing, normal users receive the standard retake state.

## Camera Requirements

Browser camera access requires HTTPS in production. Localhost is allowed by modern browsers for development.

The camera flow:

1. User clicks `Scan an item`.
2. The app requests camera permission and uses the rear camera on mobile when available.
3. User places one item inside the centered guide.
4. The app samples that region automatically and waits for a sufficiently confident, stable result.
5. Uncertain frames stay in the camera flow and ask the user to reposition the item; there is no crop or confirmation step.

The app does not continuously send video frames anywhere.

## Adding A Waste Item

1. Add the item to `src/data/referenceData.ts`.
2. Add Vietnamese and English aliases.
3. Add the material and category.
4. Add condition questions if the item needs user clarification.
5. Add one or more disposal rules.
6. Add or update `supabase/seed.sql`.
7. Add a unit test if the item affects sorting logic.

## Adding A Disposal Rule

Rules must include:

- item code
- condition key
- destination bin
- short and detailed instructions
- preparation checklist
- component actions when parts go to different bins
- warning when applicable
- verification status

The rule engine selects the highest-priority active verified rule. It throws an error if no verified rule exists.

## Adding A Reuse Suggestion

Reuse suggestions are curated data, not AI-generated.

Add:

- title
- short summary
- required condition
- prohibited condition
- up to five steps
- safety note
- difficulty
- estimated minutes

The UI shows a maximum of two safe suggestions.

## Testing

Run unit tests:

```bash
pnpm test
```

Run type checking:

```bash
pnpm typecheck
```

Run the production build:

```bash
pnpm build
```

Run Playwright browser tests:

```bash
pnpm test:e2e
```

The Playwright suite runs in mock vision mode and covers:

- uploaded-image success flow
- AI failure and retake
- manual search
- plastic cup condition flow
- special-handling item flow
- camera permission denied
- scan another item

## Deployment To Vercel

1. Push this project to a Git repository.
2. Create a Vercel project.
3. Set the environment variables in Vercel.
4. Add the trained ONNX model and `labels.json` to `public/models/`.
5. Deploy with the Vite defaults:
   - build command: `pnpm build`
   - output directory: `dist`

## Current Limitations

- The checked-in 40-class v61 ensemble is a candidate MVP (72.1% held-out top-1), not a production safety system.
- `disposable_cutlery` is searchable but not yet a v61 model output; include it in the next controlled candidate.
- Several rare classes still have too few reviewed original images; see `training/HUONG_DAN_TRAIN_AI.md` before retraining or publishing accuracy claims.
- Recognition accuracy depends on representative field data and controlled field evaluation through the actual camera frame.
- Cloud vision providers are intentionally not used in the default flow.
- Font and final icon style are placeholders and can be swapped later.
- Supabase is optional for the local demo because reference data is bundled in the app.
- Future cloud inference providers would need rate limiting and privacy review.
