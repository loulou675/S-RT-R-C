import type { VisionProvider } from './types'

let onnxProviderPromise: Promise<VisionProvider> | undefined

export async function createVisionProvider(mockItemCode?: string): Promise<VisionProvider> {
  if (import.meta.env.VITE_USE_MOCK_VISION === 'true') {
    const { MockVisionProvider } = await import('./mockVisionProvider')
    return new MockVisionProvider(mockItemCode ?? 'plastic_water_bottle')
  }

  onnxProviderPromise ??= import('./onnxVisionProvider').then(({ OnnxVisionProvider }) => new OnnxVisionProvider())
  return onnxProviderPromise
}

export type { VisionProvider, VisionResult } from './types'
