import type { VisionProvider } from './types'

export async function createVisionProvider(mockItemCode?: string): Promise<VisionProvider> {
  if (import.meta.env.VITE_USE_MOCK_VISION === 'true') {
    const { MockVisionProvider } = await import('./mockVisionProvider')
    return new MockVisionProvider(mockItemCode ?? 'plastic_water_bottle')
  }

  const { OnnxVisionProvider } = await import('./onnxVisionProvider')
  return new OnnxVisionProvider()
}

export type { VisionProvider, VisionResult } from './types'
