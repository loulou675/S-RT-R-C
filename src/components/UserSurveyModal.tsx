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

const scaleOptions = ['1', '2', '3', '4', '5']
const navigationOptions = [
  'Finding the scan feature (Tìm chức năng quét)',
  'Reading the result (Đọc kết quả)',
  'Scanning another item (Quét thêm vật khác)',
  'Using the navigation bar (Dùng thanh điều hướng)',
  'Nothing was difficult (Không có phần nào khó)',
]
const improvementOptions = [
  'Recognition accuracy (Độ chính xác nhận diện)',
  'Scanning speed (Tốc độ quét)',
  'Result explanation (Giải thích kết quả)',
  'Visual design (Thiết kế giao diện)',
  'Other (Khác)',
]

export function UserSurveyModal({ inputMethod, predictedItemCode, destinationBinCode, onClose }: UserSurveyModalProps) {
  const [scanningEase, setScanningEase] = useState('')
  const [guidanceClarity, setGuidanceClarity] = useState('')
  const [resultTrust, setResultTrust] = useState('')
  const [confusionPoint, setConfusionPoint] = useState('')
  const [confusionDetails, setConfusionDetails] = useState('')
  const [improvementPriority, setImprovementPriority] = useState('')
  const [additionalFeedback, setAdditionalFeedback] = useState('')
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
      confusionDetails: formatOpenFeedback(confusionDetails, additionalFeedback),
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
              <p className="eyebrow">Quick feedbacks</p>
              <h2 id="survey-title">How was your first scan?</h2>
              <p>Your answers help us improve SỌRT RÁC.</p>
            </header>

            <div className="survey-question-list">
              <SurveyScaleQuestion
                number="1"
                label="How easy was it to complete the waste identification process? (Bạn thấy quá trình nhận diện rác dễ đến mức nào?)"
                value={scanningEase}
                leftLabel="Very difficult (Rất khó)"
                rightLabel="Very easy (Rất dễ)"
                onChange={setScanningEase}
              />
              <SurveyScaleQuestion
                number="2"
                label="How clear was the disposal guidance? (Hướng dẫn phân loại rõ ràng đến mức nào?)"
                value={guidanceClarity}
                leftLabel="Very unclear (Rất khó hiểu)"
                rightLabel="Very clear (Rất rõ ràng)"
                onChange={setGuidanceClarity}
              />
              <SurveyScaleQuestion
                number="3"
                label="How much do you trust this result? (Bạn tin kết quả này đến mức nào?)"
                value={resultTrust}
                leftLabel="Do not trust (Không tin)"
                rightLabel="Fully trust (Hoàn toàn tin)"
                onChange={setResultTrust}
              />
              <SurveyQuestion
                number="4"
                label="Which part of the interface was hardest to use? (Phần nào của giao diện khó sử dụng nhất?)"
                value={confusionPoint}
                options={navigationOptions}
                onChange={setConfusionPoint}
              />
              {confusionPoint ? (
                <label className="survey-why">
                  <span>Could you tell us why? (Bạn có thể nói rõ hơn không?) <small>Optional / Không bắt buộc</small></span>
                  <textarea value={confusionDetails} onChange={(event) => setConfusionDetails(event.target.value)} placeholder="Tell us what felt difficult or unclear" rows={2} maxLength={200} />
                </label>
              ) : null}
              <SurveyQuestion
                number="5"
                label="What should we improve first? (Nên ưu tiên cải thiện điều gì?)"
                value={improvementPriority}
                options={improvementOptions}
                onChange={setImprovementPriority}
              />
              <label className="survey-why survey-general-feedback">
                <span>What is one change that would make SỌRT RÁC better for you? (Một thay đổi nào sẽ khiến SỌRT RÁC tốt hơn với bạn?) <small>Optional / Không bắt buộc</small></span>
                <textarea value={additionalFeedback} onChange={(event) => setAdditionalFeedback(event.target.value)} placeholder="Share any idea, concern, or suggestion" rows={3} maxLength={200} />
              </label>
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

function formatOpenFeedback(navigationDetails: string, additionalFeedback: string) {
  const entries = [
    navigationDetails.trim() ? `Navigation detail: ${navigationDetails.trim()}` : '',
    additionalFeedback.trim() ? `Additional feedback: ${additionalFeedback.trim()}` : '',
  ].filter(Boolean)

  return entries.length ? entries.join('\n\n') : undefined
}

function SurveyScaleQuestion({
  number,
  label,
  value,
  leftLabel,
  rightLabel,
  onChange,
}: {
  number: string
  label: string
  value: string
  leftLabel: string
  rightLabel: string
  onChange: (value: string) => void
}) {
  return (
    <fieldset className="survey-question">
      <legend><span>{number}</span>{label}<b aria-label="Required">*</b></legend>
      <div className="survey-scale">
        <div className="survey-scale-numbers" aria-hidden="true">
          {scaleOptions.map((option) => <span key={option}>{option}</span>)}
        </div>
        <div className="survey-scale-row">
          <div className="survey-scale-options">
            {scaleOptions.map((option) => (
              <label className={value === option ? 'survey-scale-option selected' : 'survey-scale-option'} key={option}>
                <input type="radio" name={`survey-${number}`} value={option} checked={value === option} onChange={() => onChange(option)} required />
                <span aria-hidden="true" />
              </label>
            ))}
          </div>
          <div className="survey-scale-endpoints">
            <span className="survey-scale-anchor survey-scale-anchor-left">{leftLabel}</span>
            <span className="survey-scale-anchor survey-scale-anchor-right">{rightLabel}</span>
          </div>
        </div>
      </div>
    </fieldset>
  )
}

function SurveyQuestion({ number, label, value, options, onChange }: { number: string; label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <fieldset className="survey-question">
      <legend><span>{number}</span>{label}<b aria-label="Required">*</b></legend>
      <div className="survey-options">
        {options.map((option) => (
          <label className={value === option ? 'survey-option selected' : 'survey-option'} key={option}>
            <input type="radio" name={`survey-${number}`} value={option} checked={value === option} onChange={() => onChange(option)} required />
            <span>{option}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
