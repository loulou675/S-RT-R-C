import { ImageUp, RotateCcw, Search, Home } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useFlow } from '../app/useFlow'
import { messageForError } from '../lib/errors'

export function ErrorPage() {
  const navigate = useNavigate()
  const { state, resetFlow } = useFlow()

  return (
    <section className="flow-layout narrow">
      <div className="error-panel">
        <p className="eyebrow">Try again</p>
        <h1>{messageForError(state.errorCode)}</h1>
      </div>
      <div className="action-stack">
        <button type="button" className="primary-action large" onClick={() => navigate('/scan')}>
          <RotateCcw size={19} aria-hidden="true" />
          Retake photo
        </button>
        <button type="button" className="secondary-action large" onClick={() => navigate('/scan')}>
          <ImageUp size={19} aria-hidden="true" />
          Upload another image
        </button>
        <button type="button" className="ghost-action large" onClick={() => navigate('/search')}>
          <Search size={19} aria-hidden="true" />
          Search manually
        </button>
        <button
          type="button"
          className="ghost-action large"
          onClick={() => {
            resetFlow()
            navigate('/')
          }}
        >
          <Home size={19} aria-hidden="true" />
          Return home
        </button>
      </div>
    </section>
  )
}
