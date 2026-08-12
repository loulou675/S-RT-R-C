import { describe, expect, it } from 'vitest'
import { parseComponentDetections } from '../providers/vision/onnxComponentProvider'

describe('component detection output', () => {
  it('parses detections and calculates the visible area ratio', () => {
    const result = parseComponentDetections(
      [
        0, 0, 320, 640, 0.92, 0,
        100, 100, 200, 200, 0.81, 1,
      ],
      [1, 2, 6],
      [
        { index: 0, code: 'carton_body' },
        { index: 1, code: 'plastic_cap' },
      ],
      0.45,
    )

    expect(result.map((component) => component.code)).toEqual(['carton_body', 'plastic_cap'])
    expect(result[0]?.areaRatio).toBeCloseTo(0.5)
  })

  it('filters weak detections and keeps the strongest box for each part', () => {
    const result = parseComponentDetections(
      [
        0, 0, 50, 50, 0.32, 0,
        0, 0, 100, 100, 0.7, 0,
        0, 0, 140, 140, 0.9, 0,
      ],
      [1, 3, 6],
      [{ index: 0, code: 'plastic_cap' }],
      0.45,
    )

    expect(result).toHaveLength(1)
    expect(result[0]?.confidence).toBe(0.9)
  })
})
