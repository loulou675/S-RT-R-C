import type { VisionProvider } from './types'

let onnxProviderPromise: Promise<VisionProvider> | undefined

export async function createVisionProvider(mockItemCode?: string): Promise<VisionProvider> {
  if (import.meta.env.VITE_USE_MOCK_VISION === 'true') {
    const { MockVisionProvider } = await import('./mockVisionProvider')
    return new MockVisionProvider(
      mockItemCode ?? import.meta.env.VITE_MOCK_VISION_RESULT ?? 'plastic_water_bottle',
    )
  }

  onnxProviderPromise ??= import('./onnxVisionProvider').then(({ OnnxVisionProvider }) => new OnnxVisionProvider())
  return onnxProviderPromise
}

/**
 * Allows one clean retry when a browser fails to initialise an ONNX session.
 * This is particularly useful on mobile Safari after a transient cache or
 * memory-pressure failure.
 */
export function resetVisionProvider() {
  onnxProviderPromise = undefined
}

export type { VisionProvider, VisionResult } from './types'
