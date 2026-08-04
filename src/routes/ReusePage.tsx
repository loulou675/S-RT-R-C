import { ArrowLeft, Clock, Gauge } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import { EmptyState } from '../components/EmptyState'
import { reuseSuggestions } from '../data/referenceData'

export function ReusePage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const suggestion = reuseSuggestions.find((entry) => entry.code === id)

  if (!suggestion) {
    return (
      <EmptyState title="Suggestion not found">
        Return to the result page and choose another reuse idea.
      </EmptyState>
    )
  }

  return (
    <section className="flow-layout narrow">
      <button type="button" className="ghost-action self-start" onClick={() => navigate(-1)}>
        <ArrowLeft size={17} aria-hidden="true" />
        Back
      </button>
      <div className="page-heading">
        <p className="eyebrow">Reuse suggestion</p>
        <h1>{suggestion.titleEn}</h1>
        <p>{suggestion.summaryEn}</p>
      </div>
      <div className="meta-row">
        <span>
          <Gauge size={16} aria-hidden="true" />
          {suggestion.difficulty}
        </span>
        <span>
          <Clock size={16} aria-hidden="true" />
          {suggestion.estimatedMinutes} min
        </span>
      </div>
      <section className="result-section">
        <h2>Steps</h2>
        <ol className="numbered-list">
          {suggestion.stepsEn.slice(0, 5).map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>
      <section className="warning-strip">
        <strong>Safety note</strong>
        <p>{suggestion.safetyNoteEn}</p>
      </section>
    </section>
  )
}
