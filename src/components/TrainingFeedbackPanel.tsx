import { Check, Download, MessageSquareWarning, Send } from 'lucide-react'
import { useMemo, useState } from 'react'
import { yoloClassCodes } from '../config/modelClasses'
import { trainingModeEnabled } from '../config/trainingMode'
import { wasteItems } from '../data/referenceData'
import type { AppErrorCode } from '../lib/errors'
import { downloadTrainingFeedback, readTrainingFeedback, saveTrainingFeedback } from '../services/trainingFeedback'
import type { InputMethod } from '../types/domain'

interface TrainingFeedbackPanelProps {
  imagePreview?: string
  predictedItemCode?: string
  errorCode?: AppErrorCode
  inputMethod?: InputMethod
  onCorrected?: (itemCode: string) => void
}

export function TrainingFeedbackPanel({ imagePreview, predictedItemCode, errorCode, inputMethod, onCorrected }: TrainingFeedbackPanelProps) {
  const [correctedItemCode, setCorrectedItemCode] = useState('')
  const [note, setNote] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string>()
  const itemOptions = useMemo(
    () => wasteItems
      .filter((item) => item.isActive && yoloClassCodes.includes(item.code as (typeof yoloClassCodes)[number]))
      .sort((left, right) => left.nameEn.localeCompare(right.nameEn)),
    [],
  )

  if (!trainingModeEnabled || !imagePreview) return null

  const preview = imagePreview
  const predictedLabel = wasteItems.find((item) => item.code === predictedItemCode)?.nameEn
  const feedbackCount = readTrainingFeedback().length

  async function submit() {
    if (!correctedItemCode) return

    setSaving(true)
    setSaveError(undefined)
    try {
      await saveTrainingFeedback({
        imageDataUrl: preview,
        predictedItemCode,
        correctedItemCode,
        inputMethod,
        errorCode,
        note: note.trim() || undefined,
      })
      setSubmitted(true)
      onCorrected?.(correctedItemCode)
    } catch {
      setSaveError('Could not save this feedback on the device. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="training-feedback" aria-label="Training feedback">
      <div className="training-feedback-heading">
        <MessageSquareWarning size={18} aria-hidden="true" />
        <div>
          <p className="eyebrow">Training mode</p>
          <h2>{predictedLabel ? 'Was this classification correct?' : 'Help label this image'}</h2>
        </div>
      </div>
      <p className="training-feedback-copy">
        This private training control is visible only in builds with training mode enabled. Your correction stays on this device until you export it for review.
      </p>

      {submitted ? (
        <div className="training-feedback-saved" role="status">
          <Check size={17} aria-hidden="true" />
          <span>Saved for review. {feedbackCount + 1} feedback item{feedbackCount === 0 ? '' : 's'} queued.</span>
        </div>
      ) : (
        <>
          <label className="training-feedback-field">
            <span>Correct class</span>
            <select value={correctedItemCode} onChange={(event) => setCorrectedItemCode(event.target.value)}>
              <option value="">Choose the item…</option>
              {itemOptions.map((item) => (
                <option value={item.code} key={item.code}>
                  {item.nameEn}
                </option>
              ))}
            </select>
          </label>
          <label className="training-feedback-field">
            <span>Optional note</span>
            <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Lighting, object condition, or why the result was wrong" rows={2} />
          </label>
          <button type="button" className="secondary-action" onClick={submit} disabled={!correctedItemCode || saving}>
            <Send size={17} aria-hidden="true" />
            {saving ? 'Saving…' : 'Save correction'}
          </button>
          {saveError ? <p className="inline-error">{saveError}</p> : null}
        </>
      )}

      <button type="button" className="ghost-action training-feedback-export" onClick={downloadTrainingFeedback}>
        <Download size={16} aria-hidden="true" />
        Export {feedbackCount} saved item{feedbackCount === 1 ? '' : 's'}
      </button>
    </section>
  )
}
