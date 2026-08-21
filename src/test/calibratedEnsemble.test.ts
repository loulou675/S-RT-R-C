import { describe, expect, it } from 'vitest'
import { combineCalibratedProbabilities, validateCalibratedEnsembleConfig } from '../providers/vision/calibratedEnsemble'

describe('calibrated ensemble', () => {
  it('uses class-wise model weights and returns normalized probabilities', () => {
    const result = combineCalibratedProbabilities(
      [
        [0.9, 0.1],
        [0.2, 0.8],
      ],
      {
        version: 'test',
        modelPaths: ['a.onnx', 'b.onnx'],
        temperatures: [1, 1],
        theta: [
          [8, -8],
          [-8, 8],
        ],
        bias: [0, 0],
      },
      ['first', 'second'],
    )

    expect(result[0]!.score).toBeGreaterThan(0.52)
    expect(result[1]!.score).toBeGreaterThan(0.46)
    expect(result.reduce((sum, entry) => sum + entry.score, 0)).toBeCloseTo(1, 8)
  })

  it('rejects a malformed runtime config', () => {
    expect(() => validateCalibratedEnsembleConfig({ version: 'v61' })).toThrow(/malformed/)
  })
})
