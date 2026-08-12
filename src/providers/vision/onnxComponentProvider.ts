import * as ort from 'onnxruntime-web'
import { preprocessImageToTensor } from '../../lib/image-processing/preprocess'
import type { DetectedComponent } from '../../types/domain'

interface ComponentLabel {
  index: number
  code: string
}

export class OnnxComponentProvider {
  private sessionPromise?: Promise<ort.InferenceSession>
  private labelsPromise?: Promise<ComponentLabel[]>

  async detect(image: Blob | string | HTMLCanvasElement, itemCode: string): Promise<DetectedComponent[]> {
    const [session, labels] = await Promise.all([this.loadSession(), this.loadLabels()])
    const inputSize = Number(import.meta.env.VITE_COMPONENT_INPUT_SIZE ?? 640)
    const tensor = await preprocessImageToTensor(image, {
      width: inputSize,
      height: inputSize,
      normalization: 'zero-one',
      resizeMode: 'contain',
    })
    const outputName = session.outputNames[0]
    const inputName = session.inputNames[0]
    if (!inputName || !outputName) return []

    const outputs = await session.run({ [inputName]: tensor })
    const output = outputs[outputName]
    if (!output) return []

    const optionalParts = parseComponentDetections(
      Array.from(output.data as ArrayLike<number>).map(Number),
      output.dims.map(Number),
      labels,
      Number(import.meta.env.VITE_COMPONENT_MIN_ACCEPTANCE ?? 0.5),
      inputSize,
    )
    const mappedParts = optionalParts.flatMap((part) => {
      const code = componentCodeForDetection(part.code, itemCode)
      return code ? [{ ...part, code }] : []
    })
    const bodyCode = bodyCodeForItem(itemCode)
    return bodyCode
      ? [{ code: bodyCode, confidence: 1, areaRatio: 1 }, ...mappedParts]
      : mappedParts
  }

  private loadSession() {
    if (!this.sessionPromise) {
      const path =
        import.meta.env.VITE_COMPONENT_MODEL_PATH || `${import.meta.env.BASE_URL}models/waste_components.onnx`
      if (!path) return Promise.reject(new Error('Component model path is not configured'))
      this.sessionPromise = ort.InferenceSession.create(path, { executionProviders: ['wasm'] })
    }
    return this.sessionPromise
  }

  private loadLabels() {
    if (!this.labelsPromise) {
      const path =
        import.meta.env.VITE_COMPONENT_LABELS_PATH || `${import.meta.env.BASE_URL}models/component_labels.json`
      if (!path) return Promise.reject(new Error('Component labels path is not configured'))
      this.labelsPromise = fetch(path)
        .then((response) => {
          if (!response.ok) throw new Error('Component labels could not be loaded')
          return response.json()
        })
        .then((json: { labels?: ComponentLabel[] }) => json.labels ?? [])
    }
    return this.labelsPromise
  }
}

function componentCodeForDetection(detectionCode: string, itemCode: string) {
  if (detectionCode === 'closure') return closureCodeForItem(itemCode)
  if (detectionCode === 'straw') return 'straw'
  if (detectionCode === 'carton_body') return 'carton_body'
  if (detectionCode === 'cup_body') {
    return itemCode === 'paper_cup' ? 'paper_cup_body' : 'cup'
  }
  if (['bottle_body', 'can_body'].includes(detectionCode)) return 'container'
  return undefined
}

function closureCodeForItem(itemCode: string) {
  if (['plastic_takeaway_cup', 'milk_tea_cup', 'paper_cup'].includes(itemCode)) return 'lid'
  if (['drink_carton', 'plastic_water_bottle', 'plastic_soft_drink_bottle', 'glass_drink_bottle'].includes(itemCode)) {
    return 'plastic_cap'
  }
  return undefined
}

function bodyCodeForItem(itemCode: string) {
  if (itemCode === 'drink_carton') return 'carton_body'
  if (['plastic_takeaway_cup', 'milk_tea_cup'].includes(itemCode)) return 'cup'
  if (itemCode === 'paper_cup') return 'paper_cup_body'
  if (
    ['plastic_water_bottle', 'plastic_soft_drink_bottle', 'glass_drink_bottle', 'aluminium_drink_can'].includes(itemCode)
  ) {
    return 'container'
  }
  return undefined
}

export function parseComponentDetections(
  values: number[],
  dimensions: number[],
  labels: ComponentLabel[],
  minAcceptance: number,
  inputSize = 640,
): DetectedComponent[] {
  const columns = dimensions.at(-1)
  if (columns !== 6 || values.length % columns !== 0) return []

  const bestByCode = new Map<string, DetectedComponent>()
  for (let offset = 0; offset < values.length; offset += columns) {
    const [x1, y1, x2, y2, confidence, classIndex] = values.slice(offset, offset + columns)
    const label = labels.find((entry) => entry.index === Math.round(classIndex))
    if (!label || confidence < minAcceptance) continue

    const width = Math.max(0, Math.min(inputSize, x2) - Math.max(0, x1))
    const height = Math.max(0, Math.min(inputSize, y2) - Math.max(0, y1))
    const detection = {
      code: label.code,
      confidence,
      areaRatio: Math.min(1, (width * height) / (inputSize * inputSize)),
    }
    const current = bestByCode.get(label.code)
    if (!current || detection.confidence > current.confidence) bestByCode.set(label.code, detection)
  }

  return [...bestByCode.values()].sort((left, right) => right.areaRatio - left.areaRatio)
}
