import { validateImageFile } from '../../lib/validation/imageValidation'

const MAX_UPLOAD_DIMENSION = 1600

export async function fileToDataUrl(file: File) {
  const dimensions = await validateImageFile(file)

  if (Math.max(dimensions.width, dimensions.height) > MAX_UPLOAD_DIMENSION) {
    return resizeImageFile(file, dimensions)
  }

  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error ?? new Error('Image could not be read'))
    reader.readAsDataURL(file)
  })
}

async function resizeImageFile(file: File, dimensions: { width: number; height: number }) {
  const objectUrl = URL.createObjectURL(file)

  try {
    const image = new Image()
    image.decoding = 'async'
    image.src = objectUrl
    await image.decode()

    const scale = Math.min(1, MAX_UPLOAD_DIMENSION / Math.max(dimensions.width, dimensions.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(dimensions.width * scale))
    canvas.height = Math.max(1, Math.round(dimensions.height * scale))
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Canvas is unavailable')

    // A white background avoids turning transparent PNG pixels black when the
    // normalized upload is encoded as JPEG.
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/jpeg', 0.88)
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}
