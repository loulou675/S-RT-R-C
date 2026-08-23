import { X } from 'lucide-react'
import { useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type { ReactNode } from 'react'
import type { Bin, RuleEngineResult } from '../types/domain'

interface BinPanelProps {
  bin: Bin
  result?: RuleEngineResult
  compact?: boolean
  resultPanel?: boolean
  collapsed?: boolean
  onToggleCollapsed?: () => void
  onClose?: () => void
  footer?: ReactNode
}

export function BinPanel({ bin, result, compact = false, resultPanel = false, collapsed = false, onToggleCollapsed, onClose, footer }: BinPanelProps) {
  const panelRef = useRef<HTMLElement | null>(null)
  const dragRef = useRef<{ startY: number; startOffset: number; currentOffset: number; lastY: number; lastTime: number; velocity: number } | null>(null)
  const suppressClickRef = useRef(false)
  const [dragOffset, setDragOffset] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)
  const className = ['bin-panel', compact ? 'compact' : '', resultPanel ? 'result-panel' : '', collapsed ? 'collapsed' : '', dragging ? 'dragging' : '']
    .filter(Boolean)
    .join(' ')
  const heading = result?.specialHandling ? 'Hazardous' : bin.nameEn
  const panelInk = bin.code === 'special_handling' ? '#171411' : '#fffaf4'
  const visibleSteps = result?.preparationActions.slice(0, 5) ?? []
  const lastStepForComponent = new Map<string, number>()

  visibleSteps.forEach((step, index) => {
    step.components.forEach((component) => lastStepForComponent.set(component.code, index))
  })

  function collapsedOffset() {
    const panel = panelRef.current
    const panelHeight = panel?.getBoundingClientRect().height ?? window.innerHeight
    const peekHeight = panel
      ? Number.parseFloat(window.getComputedStyle(panel).getPropertyValue('--sheet-peek-height')) || 144
      : 144
    return Math.max(0, panelHeight - peekHeight)
  }

  function beginDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    if (!onToggleCollapsed || event.pointerType === 'mouse' && event.button !== 0) return

    const startOffset = collapsed ? collapsedOffset() : 0
    dragRef.current = {
      startY: event.clientY,
      startOffset,
      currentOffset: startOffset,
      lastY: event.clientY,
      lastTime: performance.now(),
      velocity: 0,
    }
    setDragOffset(startOffset)
    setDragging(true)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function moveDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current
    if (!drag) return

    const now = performance.now()
    const elapsed = Math.max(1, now - drag.lastTime)
    drag.velocity = (event.clientY - drag.lastY) / elapsed
    drag.lastY = event.clientY
    drag.lastTime = now

    const nextOffset = Math.min(collapsedOffset(), Math.max(0, drag.startOffset + event.clientY - drag.startY))
    drag.currentOffset = nextOffset
    setDragOffset(nextOffset)
  }

  function endDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current
    if (!drag) return

    const finalOffset = drag.currentOffset
    const maxOffset = collapsedOffset()
    const shouldCollapse = drag.velocity > 0.35
      ? true
      : drag.velocity < -0.35
        ? false
        : finalOffset > maxOffset * 0.42

    dragRef.current = null
    suppressClickRef.current = Math.abs(event.clientY - drag.startY) > 5
    setDragging(false)
    setDragOffset(null)

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    if (shouldCollapse !== collapsed) onToggleCollapsed?.()
  }

  return (
    <aside
      ref={panelRef}
      className={className}
      style={{
        '--bin-color': bin.colorHex,
        '--bin-ink': panelInk,
        ...(dragOffset === null ? {} : { '--sheet-drag-y': `${dragOffset}px` }),
      } as CSSProperties}
    >
      {resultPanel ? (
        <>
          <button
            type="button"
            className="sheet-handle"
            aria-label={collapsed ? 'Expand result panel' : 'Collapse result panel'}
            aria-expanded={!collapsed}
            onClick={() => {
              if (suppressClickRef.current) {
                suppressClickRef.current = false
                return
              }
              onToggleCollapsed?.()
            }}
            onPointerDown={beginDrag}
            onPointerMove={moveDrag}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          >
            <span />
          </button>
          {onClose ? (
            <button type="button" className="result-panel-close" aria-label="Close result panel" onClick={onClose}>
              <X size={19} aria-hidden="true" />
            </button>
          ) : null}
        </>
      ) : null}
      <div className="result-panel-body" aria-hidden={resultPanel && collapsed ? true : undefined}>
        <div className="result-heading">
          <p className="eyebrow">{result?.matchLevel === 'material' ? 'Material-based result' : 'This object belongs to'}</p>
          <h2>{heading}</h2>
          <p className="object-name">{result?.item.nameEn ?? 'Object name'}</p>
          {result?.specialHandling ? <p className="special-note">Special handling required</p> : null}
          {!resultPanel ? <p className="bin-color">{bin.colorName} Bin</p> : null}
        </div>

        {result ? (
          <div className="panel-card-stack steps-only">
            {result.matchLevel === 'material' ? (
              <section className="material-result-note" aria-label="Material result notice">
                <strong>Exact item not identified</strong>
                <p>This guidance comes from a separate broad-material model.</p>
              </section>
            ) : null}
            <section className="why-bin-section" aria-labelledby="why-bin-heading">
              <h3 id="why-bin-heading">Why this bin?</h3>
              <p>{result.whyCategory}</p>
            </section>
            {result.matchLevel === 'material' && result.warning ? (
              <section className="material-result-warning" aria-label="Important material guidance">
                <strong>Important</strong>
                <p>{result.warning}</p>
              </section>
            ) : null}
            <section className="steps-section">
              <h3>Preparation steps</h3>
              <ol className="numbered-step-list">
                {visibleSteps.map((step, index) => {
                  const partsToRoute = step.components.filter(
                    (component) => lastStepForComponent.get(component.code) === index,
                  )

                  return (
                    <li key={`${index}-${step.text}`}>
                      <span className="step-number" aria-hidden="true">{index + 1}</span>
                      <div className="step-copy">
                        <p>{step.text}</p>
                        {partsToRoute.length ? (
                          <ul className="step-part-routes" aria-label="Separate these parts">
                            {partsToRoute.map((component) => (
                              <li key={component.code}>
                                <i
                                  aria-hidden="true"
                                  style={{ '--route-color': component.destinationBin.colorHex } as CSSProperties}
                                />
                                <span>
                                  <strong>{component.componentEn}</strong>
                                  <small>
                                    {result.componentActions.length > 1 ? 'Separate into' : 'Place in'}{' '}
                                    {component.destinationBin.nameEn}
                                  </small>
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    </li>
                  )
                })}
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
        {footer}
      </div>
    </aside>
  )
}
