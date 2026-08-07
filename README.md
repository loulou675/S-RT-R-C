# SỌRT RÁC

SỌRT RÁC is an MVP web application for an AI-powered waste sorting assistant at the selected RMIT Vietnam waste station.

The main recognition experience runs on one page: camera, upload, preview, processing and the sliding result panel all stay inside `/`.

The repository contains the complete application and AI integration layer, but an accurate custom waste classifier requires a trained ONNX model and a dataset representative of the RMIT test environment.

## Architecture

- React, TypeScript, Vite and React Router provide the multi-route web app.
- Browser MediaDevices handles laptop and mobile camera capture after explicit user action.
- Browser Canvas handles still-image capture, cropping, resizing and RGB preprocessing.
- ONNX Runtime Web loads `/public/models/waste_classifier.onnx` for local browser inference.
- A `VisionProvider` interface separates the model from the app flow.
- Supabase Postgres stores normalized reference data, rules, condition questions, reuse suggestions and anonymous scan events.
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
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_USE_MOCK_VISION=false
VITE_AI_MODEL_PATH=/models/waste_classifier.onnx
VITE_AI_LABELS_PATH=/models/labels.json
VITE_AI_NORMALIZATION=zero-one
VITE_AI_MIN_ACCEPTANCE=0.55
VITE_AI_MIN_MARGIN=0.15
VITE_AI_SPECIAL_HANDLING_MIN_ACCEPTANCE=0.8
VITE_AI_TIMEOUT_MS=10000
VITE_TRAINING_MODE=false
```

Do not expose Supabase service-role keys in the browser.

## Private training mode

Set `VITE_TRAINING_MODE=true` only in a local or private field-test `.env.local`.
When enabled, the scan flow shows a correction form for unknown or incorrect
results and stores compact feedback images plus labels in the browser for later
export. The public/client build keeps this feature hidden when the variable is
unset or set to `false`.

After field testing, set `VITE_TRAINING_MODE=false` (or remove it) and restart
the Vite server or rebuild the app. Because Vite environment variables are
embedded at build time, a production rebuild is required before the training
controls disappear from a deployed build.

## Supabase Setup

Create a Supabase project, then apply:

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

Row Level Security is enabled. Anonymous users can read active reference data and insert scan events. They cannot modify reference tables.

Raw user images are not stored in the database.

## ONNX Model

Place files in `public/models/`:

```text
public/models/waste_classifier.onnx
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

The model should output internal item codes such as:

- `plastic_water_bottle`
- `aluminium_drink_can`
- `plastic_takeaway_cup`
- `fruit_peel`
- `cardboard_box`
- `paper_cup`
- `battery`
- `unknown`

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
2. The app requests camera permission.
3. User captures one still image.
4. User reviews the preview.
5. The image is processed only after `Use photo`.

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

- The custom ONNX classifier is not included.
- Recognition accuracy depends on the future RMIT-specific dataset and training process.
- Cloud vision providers are intentionally not used in the default flow.
- Font and final icon style are placeholders and can be swapped later.
- Supabase is optional for the local demo because reference data is bundled in the app.
- Future cloud inference providers would need rate limiting and privacy review.
