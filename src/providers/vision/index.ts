import type { VisionProvider } from './types'

let onnxProviderPromise: Promise<VisionProvider> | undefined

export async function createVisionProvider(mockItemCode?: string): Promise<VisionProvider> {
  if (import.meta.env.VITE_USE_MOCK_VISION === 'true') {
    const { MockVisionProvider } = await import('./mockVisionProvider')
    return new MockVisionProvider(
      mockItemCode || import.meta.env.VITE_MOCK_VISION_RESULT || 'plastic_water_bottle',
    )
  }

  onnxProviderPromise ??= import('./onnxVisionProvider').then(({ OnnxVisionProvider }) => new OnnxVisionProvider())
  return onnxProviderPromise
}

export type { VisionProvider, VisionResult } from './types'
