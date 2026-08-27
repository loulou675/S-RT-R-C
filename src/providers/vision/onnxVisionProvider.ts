import * as ort from 'onnxruntime-web'
import { getClassifierBin, toAppBinCode } from '../../config/classifierBins'
import { wasteItems } from '../../data/referenceData'
import { AppError } from '../../lib/errors'
import { preprocessImageToTensor } from '../../lib/image-processing/preprocess'
import { visionLabelSchema } from '../../lib/validation/schemas'
import {
  combineCalibratedProbabilities,
  combineCalibratedProbabilitiesWithClassSpecialist,
  validateCalibratedEnsembleConfig,
  type CalibratedEnsembleConfig,
} from './calibratedEnsemble'
import { selectEnsembledItem, type ScoredClass } from './ensembleSelection'
import { runOnnxExclusive } from './onnxRuntimeQueue'
import { detectPrimaryObject } from './objectDetector'
import type { VisionProvider, VisionResult } from './types'
import type { BinCode, BroadMaterialCode } from '../../types/domain'

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
  'landfill',
  'mixed_uncertain',
])

const destinationCodes = new Set<BinCode>([
  'bottle_can',
  'organic',
  'clean_plastic',
  'paper_cardboard',
  'landfill',
  'special_handling',
  'mixed_uncertain',
])

const materialDestinations: Record<BroadMaterialCode, BinCode> = {
  plastic: 'clean_plastic',
  metal: 'bottle_can',
  paper_cardboard: 'paper_cardboard',
  organic: 'organic',
  glass: 'bottle_can',
  electronic_battery: 'special_handling',
  landfill: 'landfill',
  mixed_uncertain: 'mixed_uncertain',
}

const destinationMaterials: Record<BinCode, BroadMaterialCode> = {
  bottle_can: 'metal',
  organic: 'organic',
  clean_plastic: 'plastic',
  paper_cardboard: 'paper_cardboard',
  landfill: 'landfill',
  special_handling: 'electronic_battery',
  mixed_uncertain: 'mixed_uncertain',
}

const exactBinThresholds: Record<string, { confidence: number; margin: number }> = {
  'bottle_can:agree': { confidence: 0.35, margin: 0.35 },
  'bottle_can:disagree': { confidence: 0.35, margin: 0.05 },
  'organic:agree': { confidence: 0.60, margin: 0.05 },
  'organic:disagree': { confidence: 0.35, margin: 0.05 },
  'clean_plastic:agree': { confidence: 0.35, margin: 0.65 },
  'clean_plastic:disagree': { confidence: 0.35, margin: 0.05 },
  'paper_cardboard:agree': { confidence: 0.35, margin: 0.10 },
  'paper_cardboard:disagree': { confidence: 0.35, margin: 0.05 },
  'landfill:agree': { confidence: 0.35, margin: 0.05 },
  'landfill:disagree': { confidence: 0.35, margin: 0.05 },
  'special_handling:agree': { confidence: 0.35, margin: 0.05 },
  'special_handling:disagree': { confidence: 0.35, margin: 0.05 },
}

const knownPairThresholds: Record<string, { routerConfidence: number; materialConfidence: number }> = {
  'landfill:dirty_plastic_bag': { routerConfidence: 0.50, materialConfidence: 0.60 },
  'landfill:paper_cup': { routerConfidence: 0.55, materialConfidence: 0.60 },
}

const reviewedNonMixedOverrides: Record<string, {
  destination: BinCode
  routerConfidence: number
  materialConfidence: number
}> = {
  'landfill:medicine_blister_pack': {
    destination: 'special_handling',
    routerConfidence: 0.75,
    materialConfidence: 0.55,
  },
}

const reviewedMixedOverrides: Record<string, {
  routerConfidence: number
  materialConfidence: number
  mixedConfidence: number
}> = {
  'landfill:hair_clip': {
    routerConfidence: 0.95,
    materialConfidence: 0.90,
    mixedConfidence: 0.80,
  },
}

const detectorDestinations: Record<string, BinCode> = {
  keyboard: 'special_handling',
  laptop: 'special_handling',
  mouse: 'special_handling',
  tv: 'special_handling',
  'cell phone': 'special_handling',
  umbrella: 'mixed_uncertain',
  'teddy bear': 'mixed_uncertain',
  chair: 'landfill',
  'potted plant': 'organic',
  remote: 'special_handling',
  vase: 'landfill',
  handbag: 'mixed_uncertain',
  suitcase: 'mixed_uncertain',
  bowl: 'landfill',
  'tennis racket': 'mixed_uncertain',
  clock: 'mixed_uncertain',
}

const alwaysSupportedDetectorClasses = new Set([
  'keyboard', 'laptop', 'mouse', 'tv', 'chair', 'remote', 'vase',
  'handbag', 'suitcase', 'bowl', 'tennis racket',
])

const mixedIdentityDetectorClasses = new Set(['handbag', 'suitcase', 'tennis racket'])

const unsupportedDetectorClasses = new Set([
  'backpack', 'handbag', 'suitcase', 'frisbee', 'skis', 'snowboard',
  'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard',
  'surfboard', 'tennis racket', 'chair', 'couch', 'bed', 'dining table',
  'toilet', 'teddy bear', 'umbrella', 'keyboard', 'laptop', 'mouse', 'tv',
  'clock',
])

const detectorClassNames: Record<number, string> = {
  25: 'umbrella', 26: 'handbag', 28: 'suitcase', 38: 'tennis racket',
  45: 'bowl', 56: 'chair', 58: 'potted plant', 62: 'tv', 63: 'laptop',
  64: 'mouse', 65: 'remote', 66: 'keyboard', 67: 'cell phone',
  74: 'clock', 75: 'vase', 77: 'teddy bear',
}

const exactPairMinimums: Record<string, { confidence: number; margin: number }> = {
  'landfill:sanitary_pad': { confidence: 0.754239244556427, margin: 0 },
  'landfill:medical_mask': { confidence: 0.3788126541137695, margin: 0 },
  'clean_plastic:plastic_food_container': { confidence: 0.9104931188583374, margin: 0 },
  'bottle_can:plastic_water_bottle': { confidence: 0.4732140434741974, margin: 0 },
  'landfill:fruit_peel': { confidence: 0.26430989632606505, margin: 0 },
  'clean_plastic:plastic_bag': { confidence: 0.7544924450874329, margin: 0 },
  'landfill:paper_plate': { confidence: 0.7924265099525452, margin: 0 },
  'special_handling:electronic_cable': { confidence: 0.5298750234603882, margin: 0 },
  'landfill:disposable_cutlery': { confidence: 0.8982371521949768, margin: 0 },
  'special_handling:mobile_phone': { confidence: 0.5926962924957275, margin: 0 },
  'special_handling:power_bank': { confidence: 0.5802114439964294, margin: 0 },
  'landfill:hair_clip': { confidence: 0.22427272627353667, margin: 0 },
  'landfill:paper_cup': { confidence: 0.573688490486145, margin: 0 },
}

const v73r35Policy = {
  detectorConfidence: 0.70,
  detectorArea: 0.05,
  detectorMixedSupportConfidence: 0.80,
  organicRouterConfidence: 0.85,
  organicMaterialConfidence: 0.45,
  electronicMaterialConfidence: 0.75,
  electronicRouterConflictMaximum: 0.70,
  mixedConfidence: 0.75,
  mixedRouterConfidence: 0.75,
  mixedMaterialConfidence: 0.60,
  mixedConflictVeto: 1.01,
  noAuxExactConfidence: 0.50,
  noAuxExactMargin: 0.20,
  electronicStrongConfidence: 0.75,
  electronicStrongMargin: 0.50,
  organicStrongRouterConfidence: 0.85,
  organicStrongMaterialConfidence: 0.55,
  clockMixedConfidence: 0.75,
  calibratedPaperMixedVetoConfidence: 0.70,
  calibratedPaperMixedExactMaximum: 0.45,
  bowlOrganicMaterialConfidence: 0.90,
  bowlOrganicRouterConfidence: 0.60,
  cleanPlasticMixedConflictConfidence: 0.99,
  highConfidenceRouterOverrides: {
    mixed_uncertain: { confidence: 0.85, margin: 0.85 },
    landfill: { confidence: 0.90, margin: 0.90 },
  } as Partial<Record<BinCode, { confidence: number; margin: number }>>,
}

export class OnnxVisionProvider implements VisionProvider {
  private itemAssetsPromise?: Promise<{
    sessions: ort.InferenceSession[]
    config?: CalibratedEnsembleConfig
  }>
  private labelsPromise?: Promise<LabelRecord[]>
  private binAssetsPromise?: Promise<{ session: ort.InferenceSession; labels: LabelRecord[] } | undefined>
  private materialAssetsPromise?: Promise<{ session: ort.InferenceSession; labels: Array<{ index: number; code: BroadMaterialCode }> }>
  private mixedAssetsPromise?: Promise<{ session: ort.InferenceSession; labels: LabelRecord[] }>
  private destinationAssetsPromise?: Promise<{
    session: ort.InferenceSession
    labels: Array<{ index: number; code: BinCode }>
  }>
  private componentProviderPromise?: Promise<import('./onnxComponentProvider').OnnxComponentProvider>
  private bagSpecialistSessionPromise?: Promise<ort.InferenceSession>
  private warmupPromise?: Promise<void>

  async identify(image: Blob | string | HTMLCanvasElement): Promise<VisionResult> {
    const timeoutMs = Number(import.meta.env.VITE_AI_TIMEOUT_MS ?? 60000)
    return withTimeout(this.runInference(image), timeoutMs)
  }

  async prepare() {
    if (!this.warmupPromise) {
      this.warmupPromise = (async () => {
        const [itemAssets, , binAssets] = await Promise.all([
          this.loadItemAssets(),
          this.loadLabels(),
          this.loadBinAssets(),
        ])
        const sessions = [...itemAssets.sessions, binAssets?.session].filter(
          (entry): entry is ort.InferenceSession => Boolean(entry),
        )
        if (import.meta.env.VITE_REVIEWED_ROUTER_ENABLED !== 'false') {
          const [destinationAssets, materialAssets, mixedAssets] = await Promise.all([
            this.loadDestinationAssets(),
            this.loadMaterialAssets(),
            this.loadMixedAssets(),
          ])
          sessions.push(destinationAssets.session, materialAssets.session, mixedAssets.session)
        }

        const input = new ort.Tensor('float32', new Float32Array(3 * 224 * 224), [1, 3, 224, 224])
        for (const modelSession of sessions) {
          const inputName = modelSession.inputNames[0]
          if (inputName) {
            await runOnnxExclusive(() => modelSession.run({ [inputName]: input }))
          }
        }
      })()
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
    let itemClasses = itemAssets.config
      ? combineCalibratedProbabilities(
          modelProbabilities,
          itemAssets.config,
          labels.map(({ code }) => code),
        )
      : modelProbabilities[0]!.map((score, index) => ({ score, code: labels[index]!.code }))
    if (itemAssets.config) {
      itemClasses = await this.refineBagClasses(
        modelProbabilities,
        itemClasses,
        itemAssets.config,
        labels,
        tensor,
      )
    }
    const binClasses = binAssets
      ? await this.runRawClassifier(binAssets.session, binAssets.labels.length, tensor)
          .then((scores) => scores.map((score, index) => ({ score, code: binAssets.labels[index]!.code })))
          .catch((error) => {
            console.warn('Bin classifier failed; falling back to item-only inference.', error)
            return undefined
          })
      : undefined

    let exactResult: VisionResult | undefined
    let exactError: AppError | undefined
    try {
      exactResult = binClasses
        ? this.resolveEnsembledResult(itemClasses, binClasses)
        : this.resolveItemOnlyResult(itemClasses)
    } catch (error) {
      if (!(error instanceof AppError) || !['ITEM_NOT_RECOGNISED', 'ITEM_AMBIGUOUS'].includes(error.code)) {
        throw error
      }
      exactError = error
    }

    if (import.meta.env.VITE_REVIEWED_ROUTER_ENABLED !== 'false') {
      return this.resolveReviewedRouter(image, tensor, itemClasses, exactResult, exactError)
    }
    if (exactResult) return exactResult
    return this.resolveMaterialFallback(tensor, exactError!)
  }

  private async resolveReviewedRouter(
    image: Blob | string | HTMLCanvasElement,
    tensor: ort.Tensor,
    itemClasses: ScoredClass[],
    exactResult: VisionResult | undefined,
    exactError: AppError | undefined,
  ): Promise<VisionResult> {
    const [destinationAssets, materialAssets, mixedAssets, detection] = await Promise.all([
      this.loadDestinationAssets(),
      this.loadMaterialAssets(),
      this.loadMixedAssets(),
      typeof image === 'string'
        ? detectPrimaryObject(image).catch(() => undefined)
        : Promise.resolve(undefined),
    ])
    const destinationScores = normalizeScores(
      await this.runRawClassifier(destinationAssets.session, destinationAssets.labels.length, tensor),
    )
    const materialScores = normalizeScores(
      await this.runRawClassifier(materialAssets.session, materialAssets.labels.length, tensor),
    )
    const mixedScores = normalizeScores(
      await this.runRawClassifier(mixedAssets.session, mixedAssets.labels.length, tensor),
    )
    const destinationRanked = destinationScores
      .map((score, index) => ({ score, code: destinationAssets.labels[index]!.code }))
      .sort((left, right) => right.score - left.score)
    const materialRanked = materialScores
      .map((score, index) => ({ score, code: materialAssets.labels[index]!.code }))
      .sort((left, right) => right.score - left.score)
    const mixedRanked = mixedScores
      .map((score, index) => ({ score, code: mixedAssets.labels[index]!.code }))
      .sort((left, right) => right.score - left.score)
    const destinationTop = destinationRanked[0]
    const destinationRunnerUp = destinationRanked[1]
    const materialTop = materialRanked[0]
    const materialRunnerUp = materialRanked[1]
    const mixedTop = mixedRanked[0]
    if (!destinationTop || !materialTop || !mixedTop) {
      throw new AppError('INFERENCE_FAILED', 'Reviewed router output is incomplete.')
    }

    const materialDestination = materialDestinations[materialTop.code]
    const materialMargin = materialTop.score - (materialRunnerUp?.score ?? 0)
    const destinationMargin = destinationTop.score - (destinationRunnerUp?.score ?? 0)
    const exactRanked = [...itemClasses].sort((left, right) => right.score - left.score)
    const exactTop = exactRanked[0]
    const exactRunnerUp = exactRanked[1]
    if (!exactTop) throw new AppError('INFERENCE_FAILED', 'Exact classifier output is incomplete.')
    const exactMargin = exactTop.score - (exactRunnerUp?.score ?? 0)
    const exactClassifierBin = getClassifierBin(exactTop.code)
    const exactDestination = exactClassifierBin ? toAppBinCode(exactClassifierBin) : undefined

    const binScores = new Map<BinCode, number>()
    for (const itemClass of itemClasses) {
      const classifierBin = getClassifierBin(itemClass.code)
      if (!classifierBin) continue
      const destination = toAppBinCode(classifierBin)
      if (!destination) continue
      binScores.set(destination, (binScores.get(destination) ?? 0) + itemClass.score)
    }
    const exactBins = [...binScores.entries()]
      .map(([code, score]) => ({ code, score }))
      .sort((left, right) => right.score - left.score)
    const exactBinTop = exactBins[0]
    const exactBinRunnerUp = exactBins[1]
    if (!exactBinTop) throw new AppError('INFERENCE_FAILED', 'Exact destination aggregation is incomplete.')
    const exactBinMargin = exactBinTop.score - (exactBinRunnerUp?.score ?? 0)
    const exactGroup = `${exactBinTop.code}:${exactBinTop.code === exactDestination ? 'agree' : 'disagree'}`
    const exactThreshold = exactBinThresholds[exactGroup]
    const exactBinAccepted = Boolean(
      exactThreshold
      && exactBinTop.score >= exactThreshold.confidence
      && exactBinMargin >= exactThreshold.margin,
    )
    const pair = `${exactBinTop.code}:${exactTop.code}`

    const agreedAlternative = (
      destination: BinCode,
      routerConfidence: number,
      materialConfidence: number,
    ) => destinationTop.code === destination
      && materialDestination === destination
      && destinationTop.score >= routerConfidence
      && materialTop.score >= materialConfidence

    const priorOverride = () => {
      const known = knownPairThresholds[pair]
      if (
        known
        && destinationTop.code !== 'mixed_uncertain'
        && destinationTop.code !== exactBinTop.code
        && agreedAlternative(destinationTop.code, known.routerConfidence, known.materialConfidence)
      ) return destinationTop.code
      const reviewed = reviewedNonMixedOverrides[pair]
      if (
        reviewed
        && agreedAlternative(reviewed.destination, reviewed.routerConfidence, reviewed.materialConfidence)
      ) return reviewed.destination
      const reviewedMixed = reviewedMixedOverrides[pair]
      if (
        reviewedMixed
        && agreedAlternative('mixed_uncertain', reviewedMixed.routerConfidence, reviewedMixed.materialConfidence)
        && mixedTop.code === 'mixed_material'
        && mixedTop.score >= reviewedMixed.mixedConfidence
      ) return 'mixed_uncertain' as BinCode
      return undefined
    }

    const detectorOverride = (): { destination?: BinCode; bypass: boolean } => {
      if (!detection || detection.confidence < v73r35Policy.detectorConfidence) return { bypass: false }
      if (detection.width * detection.height < v73r35Policy.detectorArea) return { bypass: false }
      const className = detectorClassNames[detection.classIndex]
      if (!className) return { bypass: false }
      const destination = detectorDestinations[className]
      if (
        className === 'bowl'
        && exactBinTop.code === 'organic'
        && materialDestination === 'organic'
        && destinationTop.code === 'organic'
        && materialTop.score >= v73r35Policy.bowlOrganicMaterialConfidence
        && destinationTop.score >= v73r35Policy.bowlOrganicRouterConfidence
      ) return { bypass: false }
      let supported = alwaysSupportedDetectorClasses.has(className)
      if (mixedIdentityDetectorClasses.has(className)) {
        supported = (materialDestination === 'mixed_uncertain' && materialTop.score >= 0.75)
          || (mixedTop.code === 'mixed_material' && mixedTop.score >= 0.75)
      }
      if (className === 'cell phone') {
        supported = destinationTop.code === 'special_handling'
          || (materialDestination === 'special_handling' && exactDestination === 'special_handling')
      } else if (className === 'clock') {
        supported = materialDestination === 'mixed_uncertain'
          || (mixedTop.code === 'mixed_material'
            && mixedTop.score >= v73r35Policy.clockMixedConfidence)
      } else if (!supported && destination === 'mixed_uncertain') {
        supported = destinationTop.code === destination
          || materialDestination === destination
          || (mixedTop.code === 'mixed_material'
            && mixedTop.score >= v73r35Policy.detectorMixedSupportConfidence)
      } else if (!supported && destination === 'organic') {
        supported = destinationTop.code === destination || materialDestination === destination
      }
      if (supported && destination) return { destination, bypass: true }
      return { bypass: unsupportedDetectorClasses.has(className) }
    }

    const highConfidenceRouterOverride = () => {
      const threshold = v73r35Policy.highConfidenceRouterOverrides[destinationTop.code]
      if (
        !threshold
        || destinationTop.code === exactBinTop.code
        || destinationTop.score < threshold.confidence
        || destinationMargin < threshold.margin
      ) return undefined
      return destinationTop.code
    }

    const pairMinimum = exactPairMinimums[pair]
    const pairVetoed = Boolean(pairMinimum && (
      exactTop.score < pairMinimum.confidence || exactMargin < pairMinimum.margin
    ))
    const resultForDestination = (destination: BinCode, confidence: number) => {
      if (
        exactResult?.kind === 'item'
        && exactDestination === destination
        && destination === exactBinTop.code
      ) return exactResult
      return this.destinationResult(destination, confidence, materialTop.code)
    }
    const feedback = (message: string): never => {
      throw new AppError('MATERIAL_NOT_RECOGNISED', message, exactError)
    }

    if (exactBinAccepted) {
      const prior = priorOverride()
      if (prior) return resultForDestination(prior, destinationTop.score)
      const detectorDecision = detectorOverride()
      if (detectorDecision.destination) {
        return resultForDestination(detectorDecision.destination, detection?.confidence ?? destinationTop.score)
      }
      const routerOverride = highConfidenceRouterOverride()
      if (routerOverride) return resultForDestination(routerOverride, destinationTop.score)
      if (
        exactBinTop.code === 'landfill'
        && exactTop.code === 'sanitary_pad'
        && materialDestination === 'mixed_uncertain'
        && destinationTop.code === 'mixed_uncertain'
      ) return feedback('The exact result conflicts with mixed-object evidence.')
      if (
        exactBinTop.code === 'landfill'
        && materialTop.code === 'organic'
        && materialTop.score >= 0.75
        && destinationTop.code === 'paper_cardboard'
      ) return feedback('The exact result conflicts with material and routing evidence.')
      if (
        exactBinTop.code === 'paper_cardboard'
        && mixedTop.code === 'mixed_material'
        && mixedTop.score >= 0.95
        && materialDestination !== 'paper_cardboard'
        && destinationTop.code !== 'paper_cardboard'
      ) return feedback('The exact paper result conflicts with mixed-material evidence.')
      if (
        exactBinTop.code === 'special_handling'
        && exactTop.code === 'electronic_cable'
        && destinationTop.code === 'landfill'
        && materialTop.code === 'electronic_battery'
        && materialTop.score < 0.70
        && mixedTop.code === 'mixed_material'
        && mixedTop.score >= 0.75
      ) return feedback('The electronic exact result lacks sufficient material support.')
      if (
        exactBinTop.code === 'organic'
        && exactTop.code === 'fruit_peel'
        && materialDestination === 'mixed_uncertain'
        && destinationTop.code === 'organic'
        && exactBinTop.score < 0.95
      ) return feedback('The organic exact result lacks sufficient destination confidence.')
      if (
        exactBinTop.code === 'landfill'
        && destinationTop.code === 'special_handling'
        && destinationTop.score >= 0.60
        && mixedTop.code === 'mixed_material'
        && mixedTop.score >= 0.95
      ) return feedback('Landfill, special-handling, and mixed-material evidence conflict.')
      if (
        exactResult?.kind === 'item'
        && exactBinTop.code === 'clean_plastic'
        && materialDestination === 'mixed_uncertain'
        && materialTop.score >= v73r35Policy.cleanPlasticMixedConflictConfidence
      ) return feedback('Mixed-material evidence conflicts with this clean-plastic exact result.')
      if (
        exactResult?.kind !== 'item'
        && pair === 'paper_cardboard:cardboard_box'
        && exactTop.score <= v73r35Policy.calibratedPaperMixedExactMaximum
        && mixedTop.code === 'mixed_material'
        && mixedTop.score >= v73r35Policy.calibratedPaperMixedVetoConfidence
      ) return feedback('Mixed-material evidence conflicts with this calibrated paper result.')
      if (
        materialTop.code === 'electronic_battery'
        && materialTop.score >= v73r35Policy.electronicStrongConfidence
        && materialMargin >= v73r35Policy.electronicStrongMargin
        && exactBinTop.code === 'paper_cardboard'
      ) return resultForDestination('special_handling', materialTop.score)
      if (
        destinationTop.code === 'organic'
        && materialDestination === 'organic'
        && destinationTop.score >= v73r35Policy.organicStrongRouterConfidence
        && materialTop.score >= v73r35Policy.organicStrongMaterialConfidence
        && exactBinTop.code === 'landfill'
      ) return resultForDestination('organic', Math.min(destinationTop.score, materialTop.score))
      if (pairVetoed) return feedback('This exact-item lookalike did not clear its reviewed confidence floor.')
      if (exactResult?.kind === 'item' && !detectorDecision.bypass) {
        return resultForDestination(exactBinTop.code, exactBinTop.score)
      }
      if (
        destinationTop.code === 'organic'
        && materialDestination === 'organic'
        && destinationTop.score >= v73r35Policy.organicRouterConfidence
        && materialTop.score >= v73r35Policy.organicMaterialConfidence
      ) return resultForDestination('organic', Math.min(destinationTop.score, materialTop.score))
      if (
        materialTop.code === 'electronic_battery'
        && materialTop.score >= v73r35Policy.electronicMaterialConfidence
        && (destinationTop.code === 'special_handling'
          || destinationTop.score <= v73r35Policy.electronicRouterConflictMaximum)
      ) return resultForDestination('special_handling', materialTop.score)
      if (
        mixedTop.code === 'mixed_material'
        && mixedTop.score >= v73r35Policy.mixedConfidence
        && destinationTop.code === 'mixed_uncertain'
        && destinationTop.score >= v73r35Policy.mixedRouterConfidence
        && materialDestination === 'mixed_uncertain'
        && materialTop.score >= v73r35Policy.mixedMaterialConfidence
      ) return resultForDestination('mixed_uncertain', Math.min(mixedTop.score, destinationTop.score, materialTop.score))
      if (mixedTop.code === 'mixed_material' && mixedTop.score >= v73r35Policy.mixedConflictVeto) {
        return feedback('Mixed-material evidence conflicts with the exact-item result.')
      }
      if (detectorDecision.bypass) return feedback('An unsupported object was detected.')
      const auxiliaryAgrees = destinationTop.code === exactBinTop.code
        || materialDestination === exactBinTop.code
      if (
        !auxiliaryAgrees
        && (exactTop.score < v73r35Policy.noAuxExactConfidence
          || exactMargin < v73r35Policy.noAuxExactMargin)
      ) return feedback('The exact result lacked broad-classification support.')
      return resultForDestination(exactBinTop.code, exactBinTop.score)
    }

    const detectorDecision = detectorOverride()
    if (detectorDecision.destination) {
      return resultForDestination(detectorDecision.destination, detection?.confidence ?? destinationTop.score)
    }
    if (
      destinationTop.code === 'organic'
      && materialDestination === 'organic'
      && destinationTop.score >= v73r35Policy.organicRouterConfidence
      && materialTop.score >= v73r35Policy.organicMaterialConfidence
    ) return resultForDestination('organic', Math.min(destinationTop.score, materialTop.score))
    if (
      materialTop.code === 'electronic_battery'
      && materialTop.score >= v73r35Policy.electronicMaterialConfidence
      && (destinationTop.code === 'special_handling'
        || destinationTop.score <= v73r35Policy.electronicRouterConflictMaximum)
    ) return resultForDestination('special_handling', materialTop.score)
    if (
      mixedTop.code === 'mixed_material'
      && mixedTop.score >= v73r35Policy.mixedConfidence
      && destinationTop.code === 'mixed_uncertain'
      && destinationTop.score >= v73r35Policy.mixedRouterConfidence
      && materialDestination === 'mixed_uncertain'
      && materialTop.score >= v73r35Policy.mixedMaterialConfidence
    ) return resultForDestination('mixed_uncertain', Math.min(mixedTop.score, destinationTop.score, materialTop.score))
    return feedback('Exact, material, and mixed classifiers could not agree confidently.')
  }

  private destinationResult(destination: BinCode, confidence: number, material: BroadMaterialCode): VisionResult {
    const materialCode = materialDestinations[material] === destination
      ? material
      : destinationMaterials[destination]
    return { kind: 'material', materialCode, confidence }
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

      const mixedDecision = await this.resolveMixedMaterial(tensor)
      if (mixedDecision.code === 'mixed_material') {
        return {
          kind: 'material',
          materialCode: 'mixed_uncertain',
          confidence: Math.min(top.score, mixedDecision.confidence),
        }
      }

      return { kind: 'material', materialCode: top.code, confidence: Math.min(top.score, mixedDecision.confidence) }
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

  private async resolveMixedMaterial(tensor: ort.Tensor) {
    if (import.meta.env.VITE_MIXED_MODEL_ENABLED === 'false') {
      return { code: 'single_material', confidence: 1 }
    }

    const assets = await this.loadMixedAssets()
    const scores = normalizeScores(await this.runRawClassifier(assets.session, assets.labels.length, tensor))
    const ranked = scores
      .map((score, index) => ({ score, code: assets.labels[index]!.code }))
      .sort((left, right) => right.score - left.score)
    const top = ranked[0]
    const minimum = Number(import.meta.env.VITE_MIXED_MIN_ACCEPTANCE ?? 0.53)
    if (!top || top.score < minimum) {
      throw new AppError('MATERIAL_NOT_RECOGNISED', 'Mixed-material decision was uncertain.')
    }
    if (!['single_material', 'mixed_material'].includes(top.code)) {
      throw new AppError('MODEL_LOAD_FAILED', `Unsupported mixed-material label: ${top.code}`)
    }
    return { code: top.code, confidence: top.score }
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

  private async refineBagClasses(
    modelProbabilities: number[][],
    itemClasses: ScoredClass[],
    config: CalibratedEnsembleConfig,
    labels: LabelRecord[],
    tensor: ort.Tensor,
  ) {
    if (import.meta.env.VITE_BAG_SPECIALIST_ENABLED === 'false') return itemClasses

    const focusCodes = new Set(['plastic_bag', 'dirty_plastic_bag'])
    const triggerMass = itemClasses.reduce(
      (sum, entry) => sum + (focusCodes.has(entry.code) ? entry.score : 0),
      0,
    )
    const threshold = Number(import.meta.env.VITE_BAG_SPECIALIST_TRIGGER_MASS ?? 0.4)
    if (triggerMass < threshold) return itemClasses

    try {
      const session = await this.loadBagSpecialistSession()
      const specialistProbabilities = await this.runRawClassifier(session, labels.length, tensor)
      return combineCalibratedProbabilitiesWithClassSpecialist(
        modelProbabilities,
        config,
        labels.map(({ code }) => code),
        specialistProbabilities,
        'plastic_bag',
      )
    } catch (error) {
      console.warn('Bag specialist was skipped; using the deployed ensemble result.', error)
      return itemClasses
    }
  }

  private loadBagSpecialistSession() {
    if (!this.bagSpecialistSessionPromise) {
      const configuredPath =
        import.meta.env.VITE_BAG_SPECIALIST_MODEL_PATH
        ?? 'known_only__candidate_v86i_bag_specialist.onnx'
      const modelPath = resolveModelPath(configuredPath)
      this.bagSpecialistSessionPromise = ort.InferenceSession.create(modelPath, {
        executionProviders: ['wasm'],
      })
    }
    return this.bagSpecialistSessionPromise
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
        const modelPath = resolveModelPath(import.meta.env.VITE_AI_MODEL_PATH ?? 'waste_classifier.onnx')
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
            if (shouldUseLightweightItemModel()) {
              return this.loadLightweightItemAssets(config)
            }

            const sessions = [] as ort.InferenceSession[]
            try {
              for (const path of config.modelPaths) {
                sessions.push(
                  await ort.InferenceSession.create(resolveModelPath(path), {
                    executionProviders: ['wasm'],
                  }),
                )
              }
              return { sessions, config }
            } catch (error) {
              await Promise.allSettled(sessions.map((session) => session.release()))
              console.warn('Full ensemble could not load; switching to the lightweight item model.', error)
              return this.loadLightweightItemAssets(config)
            }
          })
          .catch((error) => {
            if (error instanceof AppError) throw error
            throw new AppError('MODEL_LOAD_FAILED', 'Calibrated ensemble failed to load', error)
          })
      }
    }

    return this.itemAssetsPromise
  }

  private async loadLightweightItemAssets(config?: CalibratedEnsembleConfig) {
    const configuredPath =
      import.meta.env.VITE_AI_LIGHTWEIGHT_MODEL_PATH
      ?? config?.modelPaths[0]
      ?? 'waste_classifier.onnx'
    try {
      const session = await ort.InferenceSession.create(resolveModelPath(configuredPath), {
        executionProviders: ['wasm'],
      })
      return { sessions: [session] }
    } catch (error) {
      throw new AppError('MODEL_LOAD_FAILED', 'Lightweight item model failed to load', error)
    }
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
    // v71e was accepted as an item-classifier ensemble. Keep the separate bin
    // classifier opt-in so its scores cannot silently change the evaluated v71e result.
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

  private loadMixedAssets() {
    if (!this.mixedAssetsPromise) {
      const modelPath =
        import.meta.env.VITE_MIXED_MODEL_PATH ?? `${import.meta.env.BASE_URL}models/waste_mixed_classifier.onnx`
      const labelsPath =
        import.meta.env.VITE_MIXED_LABELS_PATH ?? `${import.meta.env.BASE_URL}models/mixed_labels.json`
      this.mixedAssetsPromise = Promise.all([
        ort.InferenceSession.create(modelPath, { executionProviders: ['wasm'] }),
        fetch(labelsPath)
          .then((response) => {
            if (!response.ok) throw new Error('Mixed-material labels are not configured')
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
          throw new AppError('MODEL_LOAD_FAILED', 'Mixed-material model failed to load', error)
        })
    }
    return this.mixedAssetsPromise
  }

  private loadDestinationAssets() {
    if (!this.destinationAssetsPromise) {
      const modelPath =
        import.meta.env.VITE_DESTINATION_MODEL_PATH ?? `${import.meta.env.BASE_URL}models/v73r1-destination.onnx`
      const labelsPath =
        import.meta.env.VITE_DESTINATION_LABELS_PATH ?? `${import.meta.env.BASE_URL}models/v73r1-destination-labels.json`
      this.destinationAssetsPromise = Promise.all([
        ort.InferenceSession.create(modelPath, { executionProviders: ['wasm'] }),
        fetch(labelsPath)
          .then((response) => {
            if (!response.ok) throw new Error('Destination-router labels are not configured')
            return response.json()
          })
          .then((json) => {
            const parsed = visionLabelSchema.parse(json)
            const labels = Array.isArray(parsed)
              ? parsed.map((code, index) => ({ index, code }))
              : parsed.labels.map(({ index, code }) => ({ index, code }))
            if (labels.some(({ code }) => !destinationCodes.has(code as BinCode))) {
              throw new Error('Destination-router labels contain an unsupported code')
            }
            return labels as Array<{ index: number; code: BinCode }>
          }),
      ])
        .then(([session, labels]) => ({ session, labels }))
        .catch((error) => {
          throw new AppError('MODEL_LOAD_FAILED', 'Reviewed destination router failed to load', error)
        })
    }
    return this.destinationAssetsPromise
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

function resolveModelPath(path: string) {
  if (/^(?:https?:)?\/\//.test(path) || path.startsWith('blob:')) return path

  const modelFile = path
    .replace(/^\.\//, '')
    .replace(/^\/models\//, '')
    .replace(/^models\//, '')
  return `${import.meta.env.BASE_URL}models/${modelFile}`
}

function shouldUseLightweightItemModel() {
  if (import.meta.env.VITE_AI_LIGHTWEIGHT_MODE === 'true') return true
  if (import.meta.env.VITE_AI_LIGHTWEIGHT_MODE === 'false' || typeof navigator === 'undefined') return false

  const userAgent = navigator.userAgent
  const isMobileUserAgent = /Android|iPhone|iPad|iPod|Mobile/i.test(userAgent)
  const isIPadDesktopMode = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1
  return isMobileUserAgent || isIPadDesktopMode
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
