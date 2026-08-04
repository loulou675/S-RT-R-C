import { useRef } from 'react'
import type { CSSProperties } from 'react'
import type { Bin, RuleEngineResult } from '../types/domain'

interface BinPanelProps {
  bin: Bin
  result?: RuleEngineResult
  compact?: boolean
  resultPanel?: boolean
  collapsed?: boolean
  onToggleCollapsed?: () => void
}

export function BinPanel({ bin, result, compact = false, resultPanel = false, collapsed = false, onToggleCollapsed }: BinPanelProps) {
  const touchStartY = useRef<number | null>(null)
  const className = ['bin-panel', compact ? 'compact' : '', resultPanel ? 'result-panel' : '', collapsed ? 'collapsed' : '']
    .filter(Boolean)
    .join(' ')
  const heading = result?.specialHandling ? 'Hazardous' : bin.nameEn

  return (
    <aside
      className={className}
      style={{ '--bin-color': bin.colorHex } as CSSProperties}
      onTouchStart={(event) => {
        touchStartY.current = event.touches[0]?.clientY ?? null
      }}
      onTouchEnd={(event) => {
        const startY = touchStartY.current
        const endY = event.changedTouches[0]?.clientY
        touchStartY.current = null

        if (startY === null || endY === undefined || !onToggleCollapsed) return

        const deltaY = endY - startY
        if (!collapsed && deltaY > 60) onToggleCollapsed()
        if (collapsed && deltaY < -60) onToggleCollapsed()
      }}
    >
      {resultPanel ? (
        <button type="button" className="sheet-handle" aria-label={collapsed ? 'Expand result panel' : 'Collapse result panel'} onClick={onToggleCollapsed}>
          <span />
        </button>
      ) : null}
      <div>
        <p className="eyebrow">This object belongs to</p>
        <h2>{heading}</h2>
        <p className="object-name">{result?.item.nameEn ?? 'Object name'}</p>
        {result?.specialHandling ? <p className="special-note">Special handling required</p> : null}
        {!resultPanel ? <p className="bin-color">{bin.colorName} Bin</p> : null}
      </div>

      {result ? (
        <div className="panel-card-stack steps-only">
          <section className="steps-section">
            <h3>Preparation steps</h3>
            <ol className="numbered-step-list">
              {result.preparationSteps.slice(0, 5).map((step, index) => (
                <li key={step}>
                  <span aria-hidden="true">{index + 1}</span>
                  <p>{step}</p>
                </li>
              ))}
            </ol>
          </section>
        </div>
      ) : (
        <div className="instruction-card">
          <strong>Preparation steps:</strong>
          <ol>
            <li>Identify one item.</li>
            <li>Answer only relevant questions.</li>
            <li>Follow the recommended bin guidance.</li>
          </ol>
        </div>
      )}
    </aside>
  )
}
