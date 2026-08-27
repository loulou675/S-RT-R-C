import { describe, expect, it } from 'vitest'
import {
  combineCalibratedProbabilities,
  combineCalibratedProbabilitiesWithClassSpecialist,
  validateCalibratedEnsembleConfig,
} from '../providers/vision/calibratedEnsemble'

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

  it('replaces only the selected class contribution with a specialist', () => {
    const config = {
      version: 'test-specialist',
      modelPaths: ['active.onnx'],
      temperatures: [1],
      theta: [[0, 0]],
      bias: [0, 0],
    }
    const result = combineCalibratedProbabilitiesWithClassSpecialist(
      [[0.1, 0.9]],
      config,
      ['plastic_bag', 'dirty_plastic_bag'],
      [0.9, 0.1],
      'plastic_bag',
    )

    expect(result[0]!.score).toBeCloseTo(0.5, 8)
    expect(result[1]!.score).toBeCloseTo(0.5, 8)
    expect(result.reduce((sum, entry) => sum + entry.score, 0)).toBeCloseTo(1, 8)
  })

  it('matches the active ensemble when specialist alpha is zero', () => {
    const config = {
      version: 'test-specialist-off',
      modelPaths: ['active.onnx'],
      temperatures: [1],
      theta: [[0, 0]],
      bias: [0.1, -0.1],
    }
    const active = combineCalibratedProbabilities(
      [[0.7, 0.3]],
      config,
      ['plastic_bag', 'dirty_plastic_bag'],
    )
    const refined = combineCalibratedProbabilitiesWithClassSpecialist(
      [[0.7, 0.3]],
      config,
      ['plastic_bag', 'dirty_plastic_bag'],
      [0.2, 0.8],
      'plastic_bag',
      0,
    )

    expect(refined).toEqual(active)
  })
})
