import * as ort from 'onnxruntime-web'
import { toAppBinCode } from '../../config/classifierBins'
import { wasteItems } from '../../data/referenceData'
import { AppError } from '../../lib/errors'
import { preprocessImageToTensor } from '../../lib/image-processing/preprocess'
import { visionLabelSchema } from '../../lib/validation/schemas'
import {
  combineCalibratedProbabilities,
  validateCalibratedEnsembleConfig,
  type CalibratedEnsembleConfig,
} from './calibratedEnsemble'
import { selectEnsembledItem, type ScoredClass } from './ensembleSelection'
import { runOnnxExclusive } from './onnxRuntimeQueue'
import type { VisionProvider, VisionResult } from './types'
import type { BroadMaterialCode } from '../../types/domain'

// Static hosts such as GitHub Pages do not provide the isolation headers that
// SharedArrayBuffer-based WASM workers require. Keep inference single-threaded
// there while the runtime queue prevents overlapping model executions.
if (typeof crossOriginIsolated === 'undefined' || !crossOriginIsolated) {
  ort.env.wasm.numThreads = 1
  ort.env.wasm.proxy = false
}

interface LabelRecord {
  index: number
  code: string
}

const broadMaterialCodes = new Set<BroadMaterialCode>([
  'plastic',
  'metal',
  'paper_cardboard',
  'organic',
  'glass',
  'electronic_battery',
  'mixed_uncertain',
])

export class OnnxVisionProvider implements VisionProvider {
  private itemAssetsPromise?: Promise<{
    sessions: ort.InferenceSession[]
    config?: CalibratedEnsembleConfig
  }>
  private labelsPromise?: Promise<LabelRecord[]>
  private binAssetsPromise?: Promise<{ session: ort.InferenceSession; labels: LabelRecord[] } | undefined>
  private materialAssetsPromise?: Promise<{ session: ort.InferenceSession; labels: Array<{ index: number; code: BroadMaterialCode }> }>
  private componentProviderPromise?: Promise<import('./onnxComponentProvider').OnnxComponentProvider>
  private warmupPromise?: Promise<void>

  async identify(image: Blob | string | HTMLCanvasElement): Promise<VisionResult> {
    const timeoutMs = Number(import.meta.env.VITE_AI_TIMEOUT_MS ?? 60000)
    return withTimeout(this.runInference(image), timeoutMs)
  }

  async prepare() {
    if (!this.warmupPromise) {
      this.warmupPromise = Promise.all([this.loadItemAssets(), this.loadLabels(), this.loadBinAssets()]).then(
        async ([itemAssets, , binAssets]) => {
          const input = new ort.Tensor('float32', new Float32Array(3 * 224 * 224), [1, 3, 224, 224])
          const sessions = [...itemAssets.sessions, binAssets?.session].filter(
            (entry): entry is ort.InferenceSession => Boolean(entry),
          )
          for (const modelSession of sessions) {
            const inputName = modelSession.inputNames[0]
            if (inputName) {
              await runOnnxExclusive(() => modelSession.run({ [inputName]: input }))
            }
          }
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
    const [itemAssets, labels, binAssets] = await Promise.all([
      this.loadItemAssets(),
      this.loadLabels(),
      this.loadBinAssets(),
    ])
    const normalization = import.meta.env.VITE_AI_NORMALIZATION === 'imagenet' ? 'imagenet' : 'zero-one'
    const tensor = await preprocessImageToTensor(image, { width: 224, height: 224, normalization })
    const modelProbabilities = [] as number[][]
    for (const session of itemAssets.sessions) {
      modelProbabilities.push(await this.runRawClassifier(session, labels.length, tensor))
    }
    const itemClasses = itemAssets.config
      ? combineCalibratedProbabilities(
          modelProbabilities,
          itemAssets.config,
          labels.map(({ code }) => code),
        )
      : modelProbabilities[0]!.map((score, index) => ({ score, code: labels[index]!.code }))
    const binClasses = binAssets
      ? await this.runRawClassifier(binAssets.session, binAssets.labels.length, tensor)
          .then((scores) => scores.map((score, index) => ({ score, code: binAssets.labels[index]!.code })))
          .catch((error) => {
            console.warn('Bin classifier failed; falling back to item-only inference.', error)
            return undefined
          })
      : undefined

    try {
      if (binClasses) return this.resolveEnsembledResult(itemClasses, binClasses)
      return this.resolveItemOnlyResult(itemClasses)
    } catch (error) {
      if (!(error instanceof AppError) || !['ITEM_NOT_RECOGNISED', 'ITEM_AMBIGUOUS'].includes(error.code)) {
        throw error
      }
      return this.resolveMaterialFallback(tensor, error)
    }
  }

  private async resolveMaterialFallback(tensor: ort.Tensor, exactItemError: AppError): Promise<VisionResult> {
    if (import.meta.env.VITE_MATERIAL_MODEL_ENABLED === 'false') throw exactItemError

    try {
      const assets = await this.loadMaterialAssets()
      const rawScores = await this.runRawClassifier(assets.session, assets.labels.length, tensor)
      const probabilities = normalizeScores(rawScores)
      const ranked = probabilities
        .map((score, index) => ({ score, code: assets.labels[index]!.code }))
        .sort((left, right) => right.score - left.score)
      const top = ranked[0]
      const runnerUp = ranked[1]
      const minConfidence = Number(import.meta.env.VITE_MATERIAL_MIN_ACCEPTANCE ?? 0.95)
      const minMargin = Number(import.meta.env.VITE_MATERIAL_MIN_MARGIN ?? 0.05)
      const electronicMinConfidence = Number(import.meta.env.VITE_MATERIAL_ELECTRONIC_MIN_ACCEPTANCE ?? 0.70)
      const requiredConfidence = top?.code === 'electronic_battery' ? electronicMinConfidence : minConfidence

      if (
        !top ||
        top.score < requiredConfidence ||
        top.score - (runnerUp?.score ?? 0) < minMargin
      ) {
        throw new AppError(
          'MATERIAL_NOT_RECOGNISED',
          'Broad-material result did not clear its calibrated acceptance thresholds.',
          exactItemError,
        )
      }

      return { kind: 'material', materialCode: top.code, confidence: top.score }
    } catch (error) {
      if (error instanceof AppError && error.code === 'MATERIAL_NOT_RECOGNISED') throw error
      console.warn('Material fallback failed; requesting user feedback instead.', error)
      throw new AppError(
        'MATERIAL_NOT_RECOGNISED',
        'Broad-material inference could not provide a reliable result.',
        { exactItemError, materialError: error },
      )
    }
  }

  private resolveEnsembledResult(itemClasses: ScoredClass[], binClasses: ScoredClass[]): VisionResult {
    const directBinWeight = Number(import.meta.env.VITE_BIN_ENSEMBLE_WEIGHT ?? 0.53)
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
      kind: 'item',
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

    return { kind: 'item', itemCode: top.code }
  }

  private getSupportedItem(itemCode: string) {
    const supported = wasteItems.find((item) => item.code === itemCode && item.isActive && item.code !== 'unknown')
    if (!supported) {
      throw new AppError('ITEM_NOT_RECOGNISED', 'Unsupported class')
    }
    return supported
  }

  private async runRawClassifier(session: ort.InferenceSession, expectedClassCount: number, tensor: ort.Tensor) {
    const inputName = session.inputNames[0]
    const outputName = session.outputNames[0]

    if (!inputName || !outputName) {
      throw new AppError('MODEL_LOAD_FAILED', 'Model input or output names are missing')
    }

    let outputs: ort.InferenceSession.ReturnType
    try {
      outputs = await runOnnxExclusive(() => session.run({ [inputName]: tensor }))
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error('ONNX Runtime session.run failed.', error)
      }
      throw new AppError('INFERENCE_FAILED', 'ONNX inference failed', error)
    }

    const output = outputs[outputName]
    const scores = Array.from((output?.data ?? []) as ArrayLike<number>).map(Number)
    if (!scores.length || scores.some((score) => Number.isNaN(score))) {
      throw new AppError('INFERENCE_FAILED', 'Model output is malformed')
    }
    if (scores.length !== expectedClassCount) {
      throw new AppError(
        'MODEL_LOAD_FAILED',
        `Model returns ${scores.length} classes but its labels file contains ${expectedClassCount}`,
      )
    }
    return scores
  }

  private loadComponentProvider() {
    if (!this.componentProviderPromise) {
      this.componentProviderPromise = import('./onnxComponentProvider').then(
        ({ OnnxComponentProvider }) => new OnnxComponentProvider(),
      )
    }
    return this.componentProviderPromise
  }

  private loadItemAssets() {
    if (!this.itemAssetsPromise) {
      if (import.meta.env.VITE_AI_ENSEMBLE_ENABLED === 'false') {
        const modelPath =
          import.meta.env.VITE_AI_MODEL_PATH ?? `${import.meta.env.BASE_URL}models/waste_classifier.onnx`
        this.itemAssetsPromise = ort.InferenceSession.create(modelPath, { executionProviders: ['wasm'] })
          .then((session) => ({ sessions: [session] }))
          .catch((error) => {
            throw new AppError('MODEL_LOAD_FAILED', 'Model failed to load', error)
          })
      } else {
        const configPath =
          import.meta.env.VITE_AI_ENSEMBLE_CONFIG_PATH ??
          `${import.meta.env.BASE_URL}models/waste_classifier_ensemble.json`
        this.itemAssetsPromise = fetch(configPath)
          .then((response) => {
            if (!response.ok) throw new Error('Ensemble configuration is not available')
            return response.json()
          })
          .then(validateCalibratedEnsembleConfig)
          .then(async (config) => {
            const modelBase = `${import.meta.env.BASE_URL}models/`
            const sessions = [] as ort.InferenceSession[]
            for (const path of config.modelPaths) {
              const resolvedPath = /^(?:https?:)?\//.test(path) ? path : `${modelBase}${path}`
              sessions.push(
                await ort.InferenceSession.create(resolvedPath, {
                  executionProviders: ['wasm'],
                }),
              )
            }
            return { sessions, config }
          })
          .catch((error) => {
            if (error instanceof AppError) throw error
            throw new AppError('MODEL_LOAD_FAILED', 'Calibrated ensemble failed to load', error)
          })
      }
    }

    return this.itemAssetsPromise
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
    // v69 was accepted as an item-classifier ensemble. Keep the separate bin
    // classifier opt-in so its scores cannot silently change the evaluated v69 result.
    if (import.meta.env.VITE_BIN_MODEL_ENABLED !== 'true') {
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

  private loadMaterialAssets() {
    if (!this.materialAssetsPromise) {
      const modelPath =
        import.meta.env.VITE_MATERIAL_MODEL_PATH ?? `${import.meta.env.BASE_URL}models/waste_material_classifier.onnx`
      const labelsPath =
        import.meta.env.VITE_MATERIAL_LABELS_PATH ?? `${import.meta.env.BASE_URL}models/material_labels.json`
      this.materialAssetsPromise = Promise.all([
        ort.InferenceSession.create(modelPath, { executionProviders: ['wasm'] }),
        fetch(labelsPath)
          .then((response) => {
            if (!response.ok) throw new Error('Material labels are not configured')
            return response.json()
          })
          .then((json) => {
            const parsed = visionLabelSchema.parse(json)
            const labels = Array.isArray(parsed)
              ? parsed.map((code, index) => ({ index, code }))
              : parsed.labels.map(({ index, code }) => ({ index, code }))
            if (labels.some(({ code }) => !broadMaterialCodes.has(code as BroadMaterialCode))) {
              throw new Error('Material labels contain an unsupported code')
            }
            return labels as Array<{ index: number; code: BroadMaterialCode }>
          }),
      ])
        .then(([session, labels]) => ({ session, labels }))
        .catch((error) => {
          throw new AppError('MODEL_LOAD_FAILED', 'Material fallback model failed to load', error)
        })
    }
    return this.materialAssetsPromise
  }
}

function normalizeScores(scores: number[]) {
  const total = scores.reduce((sum, score) => sum + score, 0)
  if (scores.every((score) => score >= 0 && score <= 1) && total > 0.98 && total < 1.02) return scores
  const maximum = Math.max(...scores)
  const exponentials = scores.map((score) => Math.exp(score - maximum))
  const exponentialTotal = exponentials.reduce((sum, score) => sum + score, 0)
  return exponentials.map((score) => score / exponentialTotal)
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
