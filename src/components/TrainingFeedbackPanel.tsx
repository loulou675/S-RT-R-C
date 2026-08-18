import { Check, Download, MessageSquareWarning, Search, Send } from 'lucide-react'
import { useMemo, useState } from 'react'
import { trainingTargetClassCodes } from '../config/modelClasses'
import { resultFeedbackEnabled, trainingModeEnabled } from '../config/trainingMode'
import { wasteItems } from '../data/referenceData'
import type { AppErrorCode } from '../lib/errors'
import {
  automaticFeedbackUploadConfigured,
  downloadTrainingFeedback,
  readTrainingFeedback,
  saveTrainingFeedback,
} from '../services/trainingFeedback'
import type { InputMethod } from '../types/domain'

interface TrainingFeedbackPanelProps {
  imagePreview?: string
  predictedItemCode?: string
  errorCode?: AppErrorCode
  inputMethod?: InputMethod
  submittedStatus?: 'uploaded' | 'queued'
  onCorrected?: (itemCode: string, uploaded: boolean) => void
}

export function TrainingFeedbackPanel({ imagePreview, predictedItemCode, errorCode, inputMethod, submittedStatus, onCorrected }: TrainingFeedbackPanelProps) {
  const [open, setOpen] = useState(!predictedItemCode)
  const [query, setQuery] = useState('')
  const [correctedItemCode, setCorrectedItemCode] = useState('')
  const [note, setNote] = useState('')
  const [consented, setConsented] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [uploaded, setUploaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string>()

  const itemOptions = useMemo(
    () => wasteItems
      .filter((item) => item.isActive && trainingTargetClassCodes.includes(item.code as (typeof trainingTargetClassCodes)[number]))
      .sort((left, right) => left.nameEn.localeCompare(right.nameEn)),
    [],
  )
  const visibleOptions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    const unknownOption = itemOptions.find((item) => item.code === 'unknown' && item.code !== predictedItemCode)
    const matches = itemOptions
      .filter((item) => item.code !== predictedItemCode && item.code !== 'unknown')
      .filter((item) => {
        if (!normalizedQuery) return true
        return [item.nameEn, item.nameVi, ...item.aliasesEn, ...item.aliasesVi]
          .some((label) => label.toLowerCase().includes(normalizedQuery))
      })
      .slice(0, 7)

    return unknownOption ? [...matches, unknownOption] : matches
  }, [itemOptions, predictedItemCode, query])

  if (!resultFeedbackEnabled || !imagePreview) return null

  const predictedLabel = wasteItems.find((item) => item.code === predictedItemCode)?.nameEn
  const selectedItem = itemOptions.find((item) => item.code === correctedItemCode)
  const feedbackCount = readTrainingFeedback().length

  async function submit() {
    if (!correctedItemCode || !consented) return

    setSaving(true)
    setSaveError(undefined)
    try {
      const result = await saveTrainingFeedback({
        imageDataUrl: imagePreview as string,
        predictedItemCode,
        correctedItemCode,
        inputMethod,
        errorCode,
        note: note.trim() || undefined,
        consentVersion: 'feedback-v1',
      })
      setUploaded(result.uploaded)
      setSubmitted(true)
      onCorrected?.(correctedItemCode, result.uploaded)
    } catch {
      setSaveError('Could not save this correction. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  if (submitted || submittedStatus) {
    const wasUploaded = uploaded || submittedStatus === 'uploaded'
    return (
      <section className="training-feedback feedback-thanks" aria-label="Result correction">
        <div className="training-feedback-saved" role="status">
          <Check size={18} aria-hidden="true" />
          <span>
            {wasUploaded
              ? 'Thanks. Your correction was sent for review.'
              : 'Thanks. Your correction is saved and will send automatically when online.'}
          </span>
        </div>
        {trainingModeEnabled ? (
          <button type="button" className="ghost-action training-feedback-export" onClick={downloadTrainingFeedback}>
            <Download size={16} aria-hidden="true" />
            Reviewer export ({feedbackCount})
          </button>
        ) : null}
      </section>
    )
  }

  if (!open) {
    return (
      <section className="training-feedback feedback-prompt" aria-label="Result correction">
        <span>{predictedLabel ? 'Not the right item?' : 'Couldn’t identify it?'}</span>
        <button type="button" className="feedback-correction-trigger" onClick={() => setOpen(true)}>
          <span className="feedback-correction-label">Correct result</span>
        </button>
      </section>
    )
  }

  return (
    <section className="training-feedback feedback-editor" aria-label="Result correction">
      <div className="training-feedback-heading">
        <MessageSquareWarning size={18} aria-hidden="true" />
        <div>
          <p className="eyebrow">Improve this result</p>
          <h2>What is this item?</h2>
        </div>
      </div>
      <p className="training-feedback-copy">
        Choose the closest match. We review corrections before using them to train the AI.
      </p>

      <label className="feedback-search">
        <Search size={16} aria-hidden="true" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search item name"
          autoComplete="off"
        />
      </label>

      <div className="feedback-option-list" role="listbox" aria-label="Correct item">
        {visibleOptions.map((item) => {
          const selected = correctedItemCode === item.code
          return (
            <button
              type="button"
              role="option"
              aria-selected={selected}
              className={selected ? 'selected' : ''}
              onClick={() => setCorrectedItemCode(item.code)}
              key={item.code}
            >
              <span>{item.code === 'unknown' ? 'Something else / not listed' : item.nameEn}</span>
              {item.code === 'unknown' ? null : <small>{item.category}</small>}
              {selected ? <Check size={16} aria-hidden="true" /> : null}
            </button>
          )
        })}
        {visibleOptions.length === 0 ? <p className="feedback-empty">No matching item found.</p> : null}
      </div>

      {selectedItem ? (
        <label className="training-feedback-field">
          <span>{selectedItem.code === 'unknown' ? 'What is it called?' : 'Optional note'}</span>
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder={selectedItem.code === 'unknown' ? 'Enter the item name' : 'Lighting, condition, or anything unusual'}
          />
        </label>
      ) : null}

      <label className="feedback-consent">
        <input type="checkbox" checked={consented} onChange={(event) => setConsented(event.target.checked)} />
        <span>I agree to save the cropped item image and this correction for AI review.</span>
      </label>
      <p className="feedback-privacy-note">
        {automaticFeedbackUploadConfigured()
          ? 'After you send, the cropped image and correction are uploaded privately for review.'
          : 'Saved on this device. Automatic upload will start after the project review queue is connected.'}
      </p>

      <div className="feedback-actions">
        {predictedItemCode ? (
          <button type="button" className="ghost-action" onClick={() => setOpen(false)}>
            Cancel
          </button>
        ) : null}
        <button type="button" className="secondary-action" onClick={submit} disabled={!correctedItemCode || !consented || saving}>
          <Send size={16} aria-hidden="true" />
          {saving ? 'Saving…' : 'Send correction'}
        </button>
      </div>
      {saveError ? <p className="inline-error">{saveError}</p> : null}

      {trainingModeEnabled && feedbackCount > 0 ? (
        <button type="button" className="ghost-action training-feedback-export" onClick={downloadTrainingFeedback}>
          <Download size={16} aria-hidden="true" />
          Reviewer export ({feedbackCount})
        </button>
      ) : null}
    </section>
  )
}
