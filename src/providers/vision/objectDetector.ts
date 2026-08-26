import * as ort from 'onnxruntime-web'
import { runOnnxExclusive } from './onnxRuntimeQueue'

const INPUT_SIZE = 320
const CHANNELS = 3
const OUTPUT_COLUMNS = 6

export interface ObjectDetection {
  x: number
  y: number
  width: number
  height: number
  confidence: number
  classIndex: number
}

export interface FocusedObject {
  image: string
  detection?: ObjectDetection
}

interface PreparedDetectorImage {
  image: HTMLImageElement
  tensor: ort.Tensor
  sourceWidth: number
  sourceHeight: number
  scale: number
  padX: number
  padY: number
}

let sessionPromise: Promise<ort.InferenceSession> | undefined
let warmupPromise: Promise<void> | undefined

export async function prepareObjectDetector() {
  if (!objectDetectorEnabled()) return
  if (!warmupPromise) {
    warmupPromise = loadSession().then(async (session) => {
      const inputName = session.inputNames[0]
      if (!inputName) return
      const input = new ort.Tensor(
        'float32',
        new Float32Array(CHANNELS * INPUT_SIZE * INPUT_SIZE),
        [1, CHANNELS, INPUT_SIZE, INPUT_SIZE],
      )
      await runOnnxExclusive(() => session.run({ [inputName]: input }))
    })
  }
  await warmupPromise
}

export async function releaseObjectDetector() {
  const activeSession = sessionPromise
  sessionPromise = undefined
  warmupPromise = undefined
  if (!activeSession) return

  const session = await activeSession.catch(() => undefined)
  await session?.release()
}

export async function detectPrimaryObject(source: string): Promise<ObjectDetection | undefined> {
  if (!objectDetectorEnabled()) return undefined

  const [session, prepared] = await Promise.all([loadSession(), prepareDetectorImage(source)])
  const inputName = session.inputNames[0]
  const outputName = session.outputNames[0]
  if (!inputName || !outputName) throw new Error('Object detector input or output is unavailable.')

  const result = await runOnnxExclusive(() => session.run({ [inputName]: prepared.tensor }))
  const values = Array.from((result[outputName]?.data ?? []) as ArrayLike<number>).map(Number)
  const confidenceThreshold = Number(import.meta.env.VITE_OBJECT_DETECTOR_MIN_CONFIDENCE || 0.3)

  return selectPrimaryDetection(
    values,
    {
      sourceWidth: prepared.sourceWidth,
      sourceHeight: prepared.sourceHeight,
      scale: prepared.scale,
      padX: prepared.padX,
      padY: prepared.padY,
    },
    confidenceThreshold,
  )
}

export async function focusPrimaryObject(source: string): Promise<FocusedObject> {
  if (!objectDetectorEnabled()) return { image: source }

  const detection = await detectPrimaryObject(source)
  if (!detection) return { image: source }

  const image = await loadImage(source)
  const sourceWidth = image.naturalWidth || image.width
  const sourceHeight = image.naturalHeight || image.height
  const detectedWidth = detection.width * sourceWidth
  const detectedHeight = detection.height * sourceHeight
  const detectedCenterX = (detection.x + detection.width / 2) * sourceWidth
  const detectedCenterY = (detection.y + detection.height / 2) * sourceHeight
  const contextRatio = 0.14
  const cropSize = Math.min(
    sourceWidth,
    sourceHeight,
    Math.max(detectedWidth, detectedHeight) * (1 + contextRatio * 2),
  )
  const sourceX = clamp(detectedCenterX - cropSize / 2, 0, sourceWidth - cropSize)
  const sourceY = clamp(detectedCenterY - cropSize / 2, 0, sourceHeight - cropSize)
  const outputSize = 640
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')
  if (!context) return { image: source, detection }

  canvas.width = outputSize
  canvas.height = outputSize
  context.drawImage(
    image,
    sourceX,
    sourceY,
    cropSize,
    cropSize,
    0,
    0,
    outputSize,
    outputSize,
  )

  return { image: canvas.toDataURL('image/jpeg', 0.92), detection }
}

export function selectPrimaryDetection(
  values: number[],
  geometry: {
    sourceWidth: number
    sourceHeight: number
    scale: number
    padX: number
    padY: number
  },
  minimumConfidence: number,
) {
  if (values.length < OUTPUT_COLUMNS) return undefined

  const candidates: Array<ObjectDetection & { selectionScore: number }> = []
  const rowCount = Math.floor(values.length / OUTPUT_COLUMNS)

  for (let row = 0; row < rowCount; row += 1) {
    const offset = row * OUTPUT_COLUMNS
    const confidence = values[offset + 4] ?? 0
    const classIndex = Math.round(values[offset + 5] ?? -1)
    if (!Number.isFinite(confidence) || confidence < minimumConfidence) continue
    // A hand or body may be visible while an item is being held. The detector's
    // person class must not replace the waste item as the primary crop.
    if (classIndex === 0) continue

    const rawX1 = (values[offset] - geometry.padX) / geometry.scale
    const rawY1 = (values[offset + 1] - geometry.padY) / geometry.scale
    const rawX2 = (values[offset + 2] - geometry.padX) / geometry.scale
    const rawY2 = (values[offset + 3] - geometry.padY) / geometry.scale
    const x1 = clamp(rawX1 / geometry.sourceWidth, 0, 1)
    const y1 = clamp(rawY1 / geometry.sourceHeight, 0, 1)
    const x2 = clamp(rawX2 / geometry.sourceWidth, 0, 1)
    const y2 = clamp(rawY2 / geometry.sourceHeight, 0, 1)
    const width = x2 - x1
    const height = y2 - y1
    const area = width * height
    if (width <= 0 || height <= 0 || area < 0.018 || area > 0.94) continue

    const centerX = x1 + width / 2
    const centerY = y1 + height / 2
    const centerDistance = Math.hypot(centerX - 0.5, centerY - 0.5)
    if (centerDistance > 0.48) continue

    const centerScore = 1 - Math.min(1, centerDistance / 0.48)
    const sizeScore = Math.min(1, Math.sqrt(area) / 0.5)
    const selectionScore = confidence * 0.64 + centerScore * 0.27 + sizeScore * 0.09
    const paddingX = width * 0.08
    const paddingY = height * 0.08
    const paddedX1 = clamp(x1 - paddingX, 0, 1)
    const paddedY1 = clamp(y1 - paddingY, 0, 1)
    const paddedX2 = clamp(x2 + paddingX, 0, 1)
    const paddedY2 = clamp(y2 + paddingY, 0, 1)

    candidates.push({
      x: paddedX1,
      y: paddedY1,
      width: paddedX2 - paddedX1,
      height: paddedY2 - paddedY1,
      confidence,
      classIndex,
      selectionScore,
    })
  }

  const selected = candidates.sort((left, right) => right.selectionScore - left.selectionScore)[0]
  if (!selected) return undefined
  const { selectionScore: _selectionScore, ...detection } = selected
  return detection
}

async function prepareDetectorImage(source: string): Promise<PreparedDetectorImage> {
  const image = await loadImage(source)
  const sourceWidth = image.naturalWidth || image.width
  const sourceHeight = image.naturalHeight || image.height
  const scale = Math.min(INPUT_SIZE / sourceWidth, INPUT_SIZE / sourceHeight)
  const targetWidth = Math.round(sourceWidth * scale)
  const targetHeight = Math.round(sourceHeight * scale)
  const padX = (INPUT_SIZE - targetWidth) / 2
  const padY = (INPUT_SIZE - targetHeight) / 2
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) throw new Error('Canvas is unavailable for object detection.')

  canvas.width = INPUT_SIZE
  canvas.height = INPUT_SIZE
  context.fillStyle = 'rgb(114, 114, 114)'
  context.fillRect(0, 0, INPUT_SIZE, INPUT_SIZE)
  context.drawImage(image, padX, padY, targetWidth, targetHeight)

  const pixels = context.getImageData(0, 0, INPUT_SIZE, INPUT_SIZE).data
  const data = new Float32Array(CHANNELS * INPUT_SIZE * INPUT_SIZE)
  const plane = INPUT_SIZE * INPUT_SIZE
  for (let index = 0; index < plane; index += 1) {
    const pixel = index * 4
    data[index] = pixels[pixel] / 255
    data[plane + index] = pixels[pixel + 1] / 255
    data[plane * 2 + index] = pixels[pixel + 2] / 255
  }

  return {
    image,
    tensor: new ort.Tensor('float32', data, [1, CHANNELS, INPUT_SIZE, INPUT_SIZE]),
    sourceWidth,
    sourceHeight,
    scale,
    padX,
    padY,
  }
}

function loadSession() {
  if (!sessionPromise) {
    const modelPath =
      import.meta.env.VITE_OBJECT_DETECTOR_MODEL_PATH ||
      `${import.meta.env.BASE_URL}models/waste_object_detector.onnx`
    sessionPromise = ort.InferenceSession.create(modelPath, { executionProviders: ['wasm'] })
  }
  return sessionPromise
}

function objectDetectorEnabled() {
  return import.meta.env.VITE_OBJECT_DETECTOR_ENABLED !== 'false'
}

function loadImage(source: string) {
  const image = new Image()
  image.decoding = 'async'
  image.src = source
  return image.decode().then(() => image)
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value))
}
