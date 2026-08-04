import { AppError } from '../../lib/errors'
import type { VisionProvider, VisionResult } from './types'

export class MockVisionProvider implements VisionProvider {
  private readonly itemCode: string

  constructor(itemCode: string) {
    this.itemCode = itemCode
  }

  async identify(): Promise<VisionResult> {
    if (!import.meta.env.VITE_USE_MOCK_VISION || import.meta.env.VITE_USE_MOCK_VISION !== 'true') {
      throw new AppError('MODEL_NOT_CONFIGURED', 'Mock vision is disabled')
    }

    const selectedItem = sessionStorage.getItem('sot-rac-mock-item') ?? this.itemCode

    if (selectedItem === 'force_error') {
      throw new AppError('ITEM_NOT_RECOGNISED', 'Forced mock failure')
    }

    return { itemCode: selectedItem }
  }
}
