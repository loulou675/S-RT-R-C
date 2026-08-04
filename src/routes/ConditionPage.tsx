import { ArrowRight } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useFlow } from '../app/useFlow'
import { EmptyState } from '../components/EmptyState'
import { getItem, getQuestionForItem } from '../features/sorting/ruleEngine'
import type { ConditionKey } from '../types/domain'

export function ConditionPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { state, setConfirmedItem, setSelectedCondition } = useFlow()
  const itemCode = params.get('item') ?? state.confirmedItemCode ?? state.predictedItemCode
  const item = itemCode ? getItem(itemCode) : undefined
  const question = item ? getQuestionForItem(item.code) : undefined

  if (!item) {
    return (
      <EmptyState title="Item is missing">
        Search for the item again to continue.
      </EmptyState>
    )
  }

  if (!question) {
    navigate(`/result?item=${item.code}&condition=default`, { replace: true })
    return null
  }

  function answer(condition: ConditionKey) {
    if (!item) return
    setConfirmedItem(item.code)
    setSelectedCondition(condition)
    navigate(`/result?item=${item.code}&condition=${condition}`)
  }

  return (
    <section className="flow-layout narrow">
      <div className="page-heading">
        <p className="eyebrow">{item.nameEn}</p>
        <h1>{question.questionEn}</h1>
      </div>
      <div className="choice-list">
        {question.options.map((option) => (
          <button type="button" key={option.value} onClick={() => answer(option.value)}>
            <span>
              {option.labelEn}
              <small>{option.labelVi}</small>
            </span>
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        ))}
      </div>
    </section>
  )
}
