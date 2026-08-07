import { Home, RotateCcw, Search } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useFlow } from '../app/useFlow'
import { BinPanel } from '../components/BinPanel'
import { EmptyState } from '../components/EmptyState'
import { TrainingFeedbackPanel } from '../components/TrainingFeedbackPanel'
import { evaluateDisposal, getDefaultConditionForItem } from '../features/sorting/ruleEngine'
import { AppError, messageForError } from '../lib/errors'
import type { ConditionKey } from '../types/domain'

export function ResultPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { state, resetFlow } = useFlow()
  const itemCode = params.get('item') ?? state.confirmedItemCode ?? state.predictedItemCode
  const condition = (params.get('condition') as ConditionKey | null) ?? state.selectedCondition ?? (itemCode ? getDefaultConditionForItem(itemCode) : 'default')

  if (!itemCode) {
    return (
      <EmptyState title="No result yet">
        Scan or search for an item to see disposal guidance.
      </EmptyState>
    )
  }

  let result

  try {
    result = evaluateDisposal({
      siteCode: 'default_station',
      itemCode,
      conditionAnswers: { default: condition, container_state: condition, plastic_cup_condition: condition, container_condition: condition, plastic_cleanliness: condition, paper_condition: condition },
      locale: 'en',
    })
  } catch (error) {
    const code = error instanceof AppError ? error.code : 'RULE_NOT_FOUND'
    return (
      <section className="flow-layout narrow">
        <div className="error-panel">
          <p className="eyebrow">Guidance unavailable</p>
          <h1>{messageForError(code)}</h1>
        </div>
        <button type="button" className="primary-action large" onClick={() => navigate('/search')}>
          <Search size={19} aria-hidden="true" />
          Search manually
        </button>
      </section>
    )
  }

  return (
    <section className="result-layout">
      <div className="hero-copy result-copy">
        <h1>
          <span className="headline-line">Scan your waste.</span>
          <span className="headline-line italic">Know where it goes</span>
        </h1>
        <p>{result.specialHandling ? 'This item should not be placed in the five general waste bins. Please use an approved collection point or follow instructions from responsible staff.' : result.mainInstruction}</p>
        <p className="local-note">This guidance applies to the selected waste station.</p>

        <div className="button-row">
          <button type="button" className="primary-action" onClick={() => navigate('/scan')}>
            <RotateCcw size={17} aria-hidden="true" />
            Scan another item
          </button>
          <button type="button" className="secondary-action" onClick={() => navigate('/search')}>
            <Search size={17} aria-hidden="true" />
            Search another item
          </button>
          <button
            type="button"
            className="ghost-action"
            onClick={() => {
              resetFlow()
              navigate('/')
            }}
          >
            <Home size={17} aria-hidden="true" />
            Return home
          </button>
        </div>
        <TrainingFeedbackPanel
          imagePreview={state.imagePreview}
          predictedItemCode={state.predictedItemCode}
          inputMethod={state.inputMethod}
          onCorrected={(correctedCode) => navigate(`/result?item=${correctedCode}&condition=default`)}
        />
      </div>
      <BinPanel bin={result.destinationBin} result={result} resultPanel />
    </section>
  )
}
