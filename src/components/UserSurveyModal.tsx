import { Check, Send, X } from 'lucide-react'
import { useState } from 'react'
import type { InputMethod } from '../types/domain'
import { saveUserSurvey } from '../services/userSurvey'

interface UserSurveyModalProps {
  inputMethod: InputMethod
  predictedItemCode?: string
  destinationBinCode?: string
  onClose: () => void
}

const easeOptions = ['Very easy', 'Easy', 'Difficult', 'Very difficult']
const clarityOptions = ['Very clear', 'Clear', 'Unclear', 'Very unclear']
const trustOptions = ['Fully trust', 'Mostly trust', 'Not sure', 'Do not trust']
const confusionOptions = ['Scanning', 'Result category', 'Preparation steps', 'Parts separation', 'Nothing']
const improvementOptions = ['Recognition accuracy', 'Scanning speed', 'Result explanation', 'Visual design', 'Other']

export function UserSurveyModal({ inputMethod, predictedItemCode, destinationBinCode, onClose }: UserSurveyModalProps) {
  const [scanningEase, setScanningEase] = useState('')
  const [guidanceClarity, setGuidanceClarity] = useState('')
  const [resultTrust, setResultTrust] = useState('')
  const [confusionPoint, setConfusionPoint] = useState('')
  const [confusionDetails, setConfusionDetails] = useState('')
  const [improvementPriority, setImprovementPriority] = useState('')
  const [saving, setSaving] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const canSubmit = Boolean(scanningEase && guidanceClarity && resultTrust && confusionPoint && improvementPriority)

  async function submit() {
    if (!canSubmit || saving) return
    setSaving(true)
    await saveUserSurvey({
      inputMethod,
      predictedItemCode,
      destinationBinCode,
      scanningEase,
      guidanceClarity,
      resultTrust,
      confusionPoint,
      confusionDetails: confusionDetails.trim() || undefined,
      improvementPriority,
    })
    setSubmitted(true)
    setSaving(false)
  }

  return (
    <div className="survey-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="survey-dialog" role="dialog" aria-modal="true" aria-labelledby="survey-title" onMouseDown={(event) => event.stopPropagation()}>
        <button type="button" className="survey-close" aria-label="Close survey" onClick={onClose}>
          <X size={19} aria-hidden="true" />
        </button>

        {submitted ? (
          <div className="survey-success">
            <span className="survey-success-icon"><Check size={24} aria-hidden="true" /></span>
            <h2>Thanks for helping us improve.</h2>
            <p>Your feedback has been saved.</p>
            <button type="button" className="primary-action" onClick={onClose}>Done</button>
          </div>
        ) : (
          <>
            <header className="survey-header">
              <p className="eyebrow">Quick check-in</p>
              <h2 id="survey-title">How was your first scan?</h2>
              <p>Your answers help us improve SỌRT RÁC. All questions are required except the optional Why? field.</p>
            </header>

            <div className="survey-question-list">
              <SurveyQuestion number="1" label="How easy was it to scan this item?" value={scanningEase} options={easeOptions} onChange={setScanningEase} />
              <SurveyQuestion number="2" label="Was the disposal guidance clear?" value={guidanceClarity} options={clarityOptions} onChange={setGuidanceClarity} />
              <SurveyQuestion number="3" label="How much do you trust this result?" value={resultTrust} options={trustOptions} onChange={setResultTrust} />
              <SurveyQuestion number="4" label="What was the most confusing part?" value={confusionPoint} options={confusionOptions} onChange={setConfusionPoint} />
              {confusionPoint ? (
                <label className="survey-why">
                  <span>Why? <small>Optional</small></span>
                  <textarea value={confusionDetails} onChange={(event) => setConfusionDetails(event.target.value)} placeholder="Tell us what felt unclear" rows={2} maxLength={500} />
                </label>
              ) : null}
              <SurveyQuestion number="5" label="What should we improve first?" value={improvementPriority} options={improvementOptions} onChange={setImprovementPriority} />
            </div>

            <button type="button" className="primary-action survey-submit" onClick={submit} disabled={!canSubmit || saving}>
              <Send size={16} aria-hidden="true" />
              {saving ? 'Saving…' : 'Send feedback'}
            </button>
          </>
        )}
      </section>
    </div>
  )
}

function SurveyQuestion({ number, label, value, options, onChange }: { number: string; label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <fieldset className="survey-question">
      <legend><span>{number}</span>{label}</legend>
      <div className="survey-options">
        {options.map((option) => (
          <label className={value === option ? 'survey-option selected' : 'survey-option'} key={option}>
            <input type="radio" name={`survey-${number}`} value={option} checked={value === option} onChange={() => onChange(option)} />
            <span>{option}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
