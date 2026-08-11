# Reviewing user corrections

## Current temporary workflow

The correction feature is intentionally local-first. A correction stores a
640 x 640 center crop, the model prediction, the user's corrected class, input
method, optional note, consent version and timestamp. It does not upload or
train the model automatically.

For a private field-test build, set:

```text
VITE_RESULT_FEEDBACK=true
VITE_TRAINING_MODE=true
```

After a tester submits a correction, the private build shows **Reviewer
export**. Ask the tester to download the JSON file and send it through the
agreed private project channel. Do not request public social-media uploads.

For a public build, keep `VITE_TRAINING_MODE=false`. The reviewer export is
hidden. Set `VITE_RESULT_FEEDBACK=false` whenever the temporary correction UI
should be removed completely.

## Review decision for every image

Use one of these outcomes:

- **Accept**: one clear item is centered and the corrected class is accurate.
- **Relabel**: the image is useful but the user selected the wrong class.
- **Unknown**: the image is a valid hard negative or the item is outside the
  current taxonomy.
- **Reject**: the image is blank, unusably blurred, contains several competing
  objects, exposes a face or personal information, is duplicated, or has an
  uncertain label.

Never add a correction directly to the training set just because a user
submitted it. Hazardous labels should receive a second review.

## Before the next training run

1. Extract accepted images into the matching class folders.
2. Remove near-duplicates and images already present in train, validation or
   test.
3. Keep all user-contributed images from the same session in only one split.
4. Add accepted corrections to the training pool, not the fixed test set.
5. Keep a source manifest containing the feedback record ID, consent version,
   review decision and final class.
6. Retrain as a new model version and compare it with the previous checkpoint.
7. Release only when the fixed test metrics and fresh camera tests improve.

## Automatic remote queue

When Supabase is configured, consented corrections are sent automatically to
`public.training_feedback`. The associated JPEG is stored in the private
`training-feedback` bucket. The browser keeps a local outbox and retries failed
uploads, so the tester does not need to export or send JSON.

Open **Supabase Dashboard > Table Editor > training_feedback** and filter
`review_status = pending`. Open the matching `image_path` in **Storage >
training-feedback**, then make one decision: `accepted`, `relabeled`, `unknown`
or `rejected`. Only accepted and correctly relabeled records should enter the
training pool.

Before broad public collection, add an authenticated reviewer screen, a
retention/deletion rule, abuse rate limits and a clear privacy notice. Never
expose the private image bucket or review table to normal app users.
