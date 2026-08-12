import type { DetectedComponent } from '../../types/domain'

export interface VisionResult {
  itemCode: string
  components?: DetectedComponent[]
}

export interface VisionProvider {
  identify(image: Blob | string | HTMLCanvasElement): Promise<VisionResult>
  identifyComponents?: (
    image: Blob | string | HTMLCanvasElement,
    itemCode: string,
  ) => Promise<DetectedComponent[] | undefined>
  prepare?: () => Promise<void>
}
