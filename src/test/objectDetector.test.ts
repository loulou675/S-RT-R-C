import { describe, expect, it } from 'vitest'
import { selectPrimaryDetection } from '../providers/vision/objectDetector'

const squareGeometry = {
  sourceWidth: 320,
  sourceHeight: 320,
  scale: 1,
  padX: 0,
  padY: 0,
}

describe('primary object detection selection', () => {
  it('prefers the centered scan object over a higher-confidence corner object', () => {
    const detection = selectPrimaryDetection(
      [
        16, 16, 96, 96, 0.91, 39,
        92, 72, 236, 264, 0.79, 39,
      ],
      squareGeometry,
      0.3,
    )

    expect(detection?.classIndex).toBe(39)
    expect(detection?.confidence).toBeCloseTo(0.79)
    expect((detection?.x ?? 0) + (detection?.width ?? 0) / 2).toBeCloseTo(0.5125, 2)
  })

  it('does not let a visible person replace the object being scanned', () => {
    const detection = selectPrimaryDetection(
      [
        10, 10, 310, 310, 0.98, 0,
        104, 48, 220, 278, 0.72, 39,
      ],
      squareGeometry,
      0.3,
    )

    expect(detection?.classIndex).toBe(39)
  })

  it('returns no crop when every detection is below the acceptance threshold', () => {
    expect(
      selectPrimaryDetection([80, 80, 240, 240, 0.18, 39], squareGeometry, 0.3),
    ).toBeUndefined()
  })
})
