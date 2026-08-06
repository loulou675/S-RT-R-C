import * as ort from 'onnxruntime-web'
import { wasteItems } from '../../data/referenceData'
import { AppError } from '../../lib/errors'
import { preprocessImageToTensor } from '../../lib/image-processing/preprocess'
import { visionLabelSchema } from '../../lib/validation/schemas'
import type { VisionProvider, VisionResult } from './types'

interface LabelRecord {
  index: number
  code: string
}

export class OnnxVisionProvider implements VisionProvider {
  private sessionPromise?: Promise<ort.InferenceSession>
  private labelsPromise?: Promise<LabelRecord[]>

  async identify(image: Blob | string | HTMLCanvasElement): Promise<VisionResult> {
    const timeoutMs = Number(import.meta.env.VITE_AI_TIMEOUT_MS ?? 10000)
    return withTimeout(this.runInference(image), timeoutMs)
  }

  private async runInference(image: Blob | string | HTMLCanvasElement): Promise<VisionResult> {
    const [session, labels] = await Promise.all([this.loadSession(), this.loadLabels()])
    const normalization = import.meta.env.VITE_AI_NORMALIZATION === 'imagenet' ? 'imagenet' : 'zero-one'
    const tensor = await preprocessImageToTensor(image, { width: 224, height: 224, normalization })
    const inputName = session.inputNames[0]
    const outputName = session.outputNames[0]

    if (!inputName || !outputName) {
      throw new AppError('MODEL_LOAD_FAILED', 'Model input or output names are missing')
    }

    let outputs: ort.InferenceSession.ReturnType

    try {
      outputs = await session.run({ [inputName]: tensor })
    } catch (error) {
      throw new AppError('INFERENCE_FAILED', 'ONNX inference failed', error)
    }

    const output = outputs[outputName]
    const scores = Array.from((output?.data ?? []) as ArrayLike<number>).map(Number)

    if (!scores.length || scores.some((score) => Number.isNaN(score))) {
      throw new AppError('INFERENCE_FAILED', 'Model output is malformed')
    }

    const ranked = scores
      .map((score, index) => ({ score, label: labels.find((label) => label.index === index) }))
      .filter((entry): entry is { score: number; label: LabelRecord } => Boolean(entry.label))
      .sort((left, right) => right.score - left.score)

    const top = ranked[0]
    const runnerUp = ranked[1]
    const minAcceptance = Number(import.meta.env.VITE_AI_MIN_ACCEPTANCE ?? 0.55)
    const minMargin = Number(import.meta.env.VITE_AI_MIN_MARGIN ?? 0.15)

    if (!top || top.label.code === 'unknown') {
      throw new AppError('ITEM_NOT_RECOGNISED', 'Unknown class')
    }

    if (top.score < minAcceptance || (runnerUp && top.score - runnerUp.score < minMargin)) {
      throw new AppError('ITEM_AMBIGUOUS', 'Model result is uncertain')
    }

    const supported = wasteItems.find((item) => item.code === top.label.code && item.isActive && item.code !== 'unknown')

    if (!supported) {
      throw new AppError('ITEM_NOT_RECOGNISED', 'Unsupported class')
    }

    const specialHandlingMinAcceptance = Number(import.meta.env.VITE_AI_SPECIAL_HANDLING_MIN_ACCEPTANCE ?? 0.8)

    if (supported.specialHandling && top.score < specialHandlingMinAcceptance) {
      throw new AppError('ITEM_AMBIGUOUS', 'Special-handling item result is uncertain')
    }

    return { itemCode: top.label.code }
  }

  private loadSession() {
    if (!this.sessionPromise) {
      const modelPath = import.meta.env.VITE_AI_MODEL_PATH ?? `${import.meta.env.BASE_URL}models/waste_classifier.onnx`
      this.sessionPromise = fetch(modelPath, { method: 'HEAD' })
        .then((response) => {
          if (!response.ok) {
            throw new AppError('MODEL_NOT_CONFIGURED', 'AI model is not configured.')
          }
          return ort.InferenceSession.create(modelPath, { executionProviders: ['wasm'] })
        })
        .catch((error) => {
          if (error instanceof AppError) throw error
          throw new AppError('MODEL_LOAD_FAILED', 'Model failed to load', error)
        })
    }

    return this.sessionPromise
  }

  private loadLabels() {
    if (!this.labelsPromise) {
      const labelsPath = import.meta.env.VITE_AI_LABELS_PATH ?? `${import.meta.env.BASE_URL}models/labels.json`
      this.labelsPromise = fetch(labelsPath)
        .then((response) => {
          if (!response.ok) {
            throw new AppError('MODEL_NOT_CONFIGURED', 'AI labels are not configured.')
          }
          return response.json()
        })
        .then((json) => {
          const parsed = visionLabelSchema.parse(json)
          if (Array.isArray(parsed)) {
            return parsed.map((code, index) => ({ index, code }))
          }
          return parsed.labels.map(({ index, code }) => ({ index, code }))
        })
        .catch((error) => {
          if (error instanceof AppError) throw error
          throw new AppError('MODEL_LOAD_FAILED', 'Labels failed to load', error)
        })
    }

    return this.labelsPromise
  }
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number) {
  let timeoutId: number | undefined

  const timeout = new Promise<never>((_, reject) => {
    timeoutId = window.setTimeout(() => reject(new AppError('INFERENCE_TIMEOUT', 'Inference timed out')), timeoutMs)
  })

  try {
    return await Promise.race([promise, timeout])
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId)
    }
  }
}
