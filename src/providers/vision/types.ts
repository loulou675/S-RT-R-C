export interface VisionResult {
  itemCode: string
}

export interface VisionProvider {
  identify(image: Blob | string | HTMLCanvasElement): Promise<VisionResult>
}
