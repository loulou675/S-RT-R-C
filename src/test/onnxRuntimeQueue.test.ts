import { describe, expect, it } from 'vitest'
import { runOnnxExclusive } from '../providers/vision/onnxRuntimeQueue'

describe('runOnnxExclusive', () => {
  it('serializes overlapping runtime operations', async () => {
    let active = 0
    let peakActive = 0

    const operation = async () => {
      active += 1
      peakActive = Math.max(peakActive, active)
      await new Promise((resolve) => window.setTimeout(resolve, 5))
      active -= 1
    }

    await Promise.all([runOnnxExclusive(operation), runOnnxExclusive(operation), runOnnxExclusive(operation)])

    expect(peakActive).toBe(1)
  })

  it('continues processing after a failed operation', async () => {
    await expect(runOnnxExclusive(async () => Promise.reject(new Error('expected failure')))).rejects.toThrow(
      'expected failure',
    )

    await expect(runOnnxExclusive(async () => 'recovered')).resolves.toBe('recovered')
  })
})
