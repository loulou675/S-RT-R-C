import type { BinCode, BroadMaterialCode, DetectedComponent } from '../../types/domain'

export interface ItemVisionResult {
  kind: 'item'
  itemCode: string
  binCode?: BinCode
  components?: DetectedComponent[]
}

export interface MaterialVisionResult {
  kind: 'material'
  materialCode: BroadMaterialCode
  confidence: number
}

export type VisionResult = ItemVisionResult | MaterialVisionResult

export interface VisionProvider {
  identify(image: Blob | string | HTMLCanvasElement): Promise<VisionResult>
  identifyComponents?: (
    image: Blob | string | HTMLCanvasElement,
    itemCode: string,
  ) => Promise<DetectedComponent[] | undefined>
  prepare?: () => Promise<void>
}
