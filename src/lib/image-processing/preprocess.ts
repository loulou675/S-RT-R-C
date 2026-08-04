import * as ort from 'onnxruntime-web'

export interface ImagePreprocessOptions {
  width?: number
  height?: number
}

export async function preprocessImageToTensor(
  source: Blob | string | HTMLCanvasElement | HTMLImageElement,
  options: ImagePreprocessOptions = {},
) {
  const width = options.width ?? 224
  const height = options.height ?? 224
  const image = await loadImage(source)
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d', { willReadFrequently: true })

  if (!context) {
    throw new Error('Canvas is unavailable')
  }

  canvas.width = width
  canvas.height = height

  const size = Math.min(image.naturalWidth || image.width, image.naturalHeight || image.height)
  const sx = ((image.naturalWidth || image.width) - size) / 2
  const sy = ((image.naturalHeight || image.height) - size) / 2

  context.drawImage(image, sx, sy, size, size, 0, 0, width, height)

  const imageData = context.getImageData(0, 0, width, height)
  const channels = 3
  const data = new Float32Array(channels * width * height)
  const mean = [0.485, 0.456, 0.406]
  const std = [0.229, 0.224, 0.225]

  for (let index = 0; index < width * height; index += 1) {
    const pixel = index * 4
    data[index] = imageData.data[pixel] / 255 - mean[0]
    data[width * height + index] = imageData.data[pixel + 1] / 255 - mean[1]
    data[2 * width * height + index] = imageData.data[pixel + 2] / 255 - mean[2]
  }

  for (let index = 0; index < data.length; index += 1) {
    const channel = Math.floor(index / (width * height))
    data[index] = data[index] / std[channel]
  }

  return new ort.Tensor('float32', data, [1, channels, height, width])
}

async function loadImage(source: Blob | string | HTMLCanvasElement | HTMLImageElement) {
  if (source instanceof HTMLImageElement) {
    await source.decode().catch(() => undefined)
    return source
  }

  if (source instanceof HTMLCanvasElement) {
    const image = new Image()
    image.src = source.toDataURL('image/png')
    await image.decode()
    return image
  }

  const objectUrl = typeof source === 'string' ? source : URL.createObjectURL(source)
  const shouldRevoke = typeof source !== 'string'
  const image = new Image()
  image.decoding = 'async'
  image.src = objectUrl

  try {
    await image.decode()
    return image
  } finally {
    if (shouldRevoke) {
      URL.revokeObjectURL(objectUrl)
    }
  }
}
