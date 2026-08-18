import * as ort from 'onnxruntime-web'
import { toAppBinCode } from '../../config/classifierBins'
import { wasteItems } from '../../data/referenceData'
import { AppError } from '../../lib/errors'
import { preprocessImageToTensor } from '../../lib/image-processing/preprocess'
import { visionLabelSchema } from '../../lib/validation/schemas'
import { selectEnsembledItem, type ScoredClass } from './ensembleSelection'
import type { VisionProvider, VisionResult } from './types'

interface LabelRecord {
  index: number
  code: string
}

export class OnnxVisionProvider implements VisionProvider {
  private sessionPromise?: Promise<ort.InferenceSession>
  private labelsPromise?: Promise<LabelRecord[]>
  private binAssetsPromise?: Promise<{ session: ort.InferenceSession; labels: LabelRecord[] } | undefined>
  private componentProviderPromise?: Promise<import('./onnxComponentProvider').OnnxComponentProvider>
  private warmupPromise?: Promise<void>

  async identify(image: Blob | string | HTMLCanvasElement): Promise<VisionResult> {
    const timeoutMs = Number(import.meta.env.VITE_AI_TIMEOUT_MS ?? 10000)
    return withTimeout(this.runInference(image), timeoutMs)
  }

  async prepare() {
    if (!this.warmupPromise) {
      this.warmupPromise = Promise.all([this.loadSession(), this.loadLabels(), this.loadBinAssets()]).then(
        async ([session, , binAssets]) => {
          const input = new ort.Tensor('float32', new Float32Array(3 * 224 * 224), [1, 3, 224, 224])
          const sessions = [session, binAssets?.session].filter(
            (entry): entry is ort.InferenceSession => Boolean(entry),
          )
          await Promise.all(
            sessions.map((modelSession) => {
              const inputName = modelSession.inputNames[0]
              return inputName ? modelSession.run({ [inputName]: input }) : undefined
            }),
          )
        },
      )
    }
    await this.warmupPromise
  }

  async identifyComponents(image: Blob | string | HTMLCanvasElement, itemCode: string) {
    if (import.meta.env.VITE_COMPONENT_MODEL_ENABLED === 'false') return undefined

    try {
      const componentProvider = await this.loadComponentProvider()
      const componentTimeoutMs = Number(import.meta.env.VITE_COMPONENT_TIMEOUT_MS ?? 2500)
      return await withTimeout(componentProvider.detect(image, itemCode), componentTimeoutMs)
    } catch (error) {
      console.warn('Component detection was skipped; sorting rules will provide the component guide.', error)
      return undefined
    }
  }

  private async runInference(image: Blob | string | HTMLCanvasElement): Promise<VisionResult> {
    const [session, labels, binAssets] = await Promise.all([
      this.loadSession(),
      this.loadLabels(),
      this.loadBinAssets(),
    ])
    const normalization = import.meta.env.VITE_AI_NORMALIZATION === 'imagenet' ? 'imagenet' : 'zero-one'
    const tensor = await preprocessImageToTensor(image, { width: 224, height: 224, normalization })
    const [itemClasses, binClasses] = await Promise.all([
      this.runClassifier(session, labels, tensor),
      binAssets
        ? this.runClassifier(binAssets.session, binAssets.labels, tensor).catch((error) => {
            console.warn('Bin classifier failed; falling back to item-only inference.', error)
            return undefined
          })
        : undefined,
    ])

    if (binClasses) {
      return this.resolveEnsembledResult(itemClasses, binClasses)
    }

    return this.resolveItemOnlyResult(itemClasses)
  }

  private resolveEnsembledResult(itemClasses: ScoredClass[], binClasses: ScoredClass[]): VisionResult {
    const directBinWeight = Number(import.meta.env.VITE_BIN_ENSEMBLE_WEIGHT ?? 0.49)
    const selected = selectEnsembledItem(itemClasses, binClasses, directBinWeight)
    const minBinAcceptance = Number(import.meta.env.VITE_BIN_MIN_ACCEPTANCE ?? 0.45)
    const minBinMargin = Number(import.meta.env.VITE_BIN_MIN_MARGIN ?? 0.05)
    const minItemAcceptance = Number(import.meta.env.VITE_AI_WITHIN_BIN_MIN_ACCEPTANCE ?? 0.18)
    const minItemMargin = Number(import.meta.env.VITE_AI_WITHIN_BIN_MIN_MARGIN ?? 0.02)

    if (!selected) {
      throw new AppError('ITEM_NOT_RECOGNISED', 'Unknown class')
    }

    if (
      selected.binScore < minBinAcceptance ||
      selected.binMargin < minBinMargin ||
      selected.itemScore < minItemAcceptance ||
      selected.itemMargin < minItemMargin
    ) {
      throw new AppError('ITEM_AMBIGUOUS', 'Model result is uncertain')
    }

    const supported = this.getSupportedItem(selected.itemCode)
    const specialHandlingMinAcceptance = Number(import.meta.env.VITE_AI_SPECIAL_HANDLING_MIN_ACCEPTANCE ?? 0.8)

    if (supported.specialHandling && selected.itemScore < specialHandlingMinAcceptance) {
      throw new AppError('ITEM_AMBIGUOUS', 'Special-handling item result is uncertain')
    }

    return {
      itemCode: selected.itemCode,
      binCode: toAppBinCode(selected.binCode),
    }
  }

  private resolveItemOnlyResult(classes: ScoredClass[]): VisionResult {
    const ranked = [...classes].sort((left, right) => right.score - left.score)

    const top = ranked[0]
    const runnerUp = ranked[1]
    const minAcceptance = Number(import.meta.env.VITE_AI_MIN_ACCEPTANCE ?? 0.55)
    const minMargin = Number(import.meta.env.VITE_AI_MIN_MARGIN ?? 0.15)

    if (!top || top.code === 'unknown') {
      throw new AppError('ITEM_NOT_RECOGNISED', 'Unknown class')
    }

    if (top.score < minAcceptance || (runnerUp && top.score - runnerUp.score < minMargin)) {
      throw new AppError('ITEM_AMBIGUOUS', 'Model result is uncertain')
    }

    const supported = this.getSupportedItem(top.code)

    const specialHandlingMinAcceptance = Number(import.meta.env.VITE_AI_SPECIAL_HANDLING_MIN_ACCEPTANCE ?? 0.8)

    if (supported.specialHandling && top.score < specialHandlingMinAcceptance) {
      throw new AppError('ITEM_AMBIGUOUS', 'Special-handling item result is uncertain')
    }

    return { itemCode: top.code }
  }

  private getSupportedItem(itemCode: string) {
    const supported = wasteItems.find((item) => item.code === itemCode && item.isActive && item.code !== 'unknown')
    if (!supported) {
      throw new AppError('ITEM_NOT_RECOGNISED', 'Unsupported class')
    }
    return supported
  }

  private async runClassifier(session: ort.InferenceSession, labels: LabelRecord[], tensor: ort.Tensor) {
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
    if (scores.length !== labels.length) {
      throw new AppError(
        'MODEL_LOAD_FAILED',
        `Model returns ${scores.length} classes but its labels file contains ${labels.length}`,
      )
    }

    return scores
      .map((score, index) => ({ score, label: labels.find((label) => label.index === index) }))
      .filter((entry): entry is { score: number; label: LabelRecord } => Boolean(entry.label))
      .map(({ score, label }) => ({ score, code: label.code }))
  }

  private loadComponentProvider() {
    if (!this.componentProviderPromise) {
      this.componentProviderPromise = import('./onnxComponentProvider').then(
        ({ OnnxComponentProvider }) => new OnnxComponentProvider(),
      )
    }
    return this.componentProviderPromise
  }

  private loadSession() {
    if (!this.sessionPromise) {
      const modelPath = import.meta.env.VITE_AI_MODEL_PATH ?? `${import.meta.env.BASE_URL}models/waste_classifier.onnx`
      this.sessionPromise = ort.InferenceSession.create(modelPath, { executionProviders: ['wasm'] })
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

  private loadBinAssets() {
    if (import.meta.env.VITE_BIN_MODEL_ENABLED === 'false') {
      return Promise.resolve(undefined)
    }

    if (!this.binAssetsPromise) {
      const modelPath =
        import.meta.env.VITE_BIN_MODEL_PATH ?? `${import.meta.env.BASE_URL}models/waste_bin_classifier.onnx`
      const labelsPath = import.meta.env.VITE_BIN_LABELS_PATH ?? `${import.meta.env.BASE_URL}models/bin_labels.json`
      this.binAssetsPromise = Promise.all([
        ort.InferenceSession.create(modelPath, { executionProviders: ['wasm'] }),
        fetch(labelsPath)
          .then((response) => {
            if (!response.ok) throw new Error('Bin labels are not configured')
            return response.json()
          })
          .then((json) => {
            const parsed = visionLabelSchema.parse(json)
            return Array.isArray(parsed)
              ? parsed.map((code, index) => ({ index, code }))
              : parsed.labels.map(({ index, code }) => ({ index, code }))
          }),
      ])
        .then(([session, labels]) => ({ session, labels }))
        .catch((error) => {
          console.warn('Bin classifier is unavailable; using item-only inference.', error)
          return undefined
        })
    }

    return this.binAssetsPromise
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
