import { Check, RotateCcw, X } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useFlow } from '../app/useFlow'
import { EmptyState } from '../components/EmptyState'
import { StatusBlock } from '../components/StatusBlock'
import { createVisionProvider } from '../providers/vision'
import { toAppError } from '../lib/errors'

export function PreviewPage() {
  const navigate = useNavigate()
  const { state, setErrorCode, setPredictedItem, setImagePreview } = useFlow()
  const [status, setStatus] = useState<string | null>(null)

  if (!state.imagePreview) {
    return (
      <EmptyState title="No image selected">
        Return to scanning and capture or upload one item.
      </EmptyState>
    )
  }

  async function processImage() {
    if (!state.imagePreview) return

    try {
      setStatus('Preparing image...')
      await wait(180)
      setStatus('Identifying item...')
      const provider = await createVisionProvider(state.mockItemCode)
      const result = await provider.identify(state.imagePreview)
      setStatus('Checking disposal guidance...')
      await wait(180)
      if (result.kind === 'material') {
        navigate(`/?material=${result.materialCode}&source=vision`)
      } else {
        setPredictedItem(result.itemCode)
        navigate('/confirm')
      }
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error(error)
      }
      setErrorCode(toAppError(error, 'INFERENCE_FAILED').code)
      navigate('/scan/error')
    }
  }

  return (
    <section className="flow-layout">
      <div className="preview-frame">
        <img src={state.imagePreview} alt="Captured waste item preview" />
      </div>
      {status ? <StatusBlock message={status} /> : null}
      <div className="button-row full">
        <button type="button" className="primary-action" onClick={processImage} disabled={Boolean(status)}>
          <Check size={17} aria-hidden="true" />
          Use photo
        </button>
        <button type="button" className="secondary-action" onClick={() => navigate('/scan')} disabled={Boolean(status)}>
          <RotateCcw size={17} aria-hidden="true" />
          Retake
        </button>
        <button
          type="button"
          className="ghost-action"
          onClick={() => {
            setImagePreview(undefined)
            navigate('/')
          }}
          disabled={Boolean(status)}
        >
          <X size={17} aria-hidden="true" />
          Cancel
        </button>
      </div>
    </section>
  )
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}
