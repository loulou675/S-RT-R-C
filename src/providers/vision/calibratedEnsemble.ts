import type { ScoredClass } from './ensembleSelection'

export interface CalibratedEnsembleConfig {
  version: string
  modelPaths: string[]
  temperatures: number[]
  theta: number[][]
  bias: number[]
}

const EPSILON = 1e-12

function softmax(values: number[]) {
  const maximum = Math.max(...values)
  const exponentials = values.map((value) => Math.exp(value - maximum))
  const total = exponentials.reduce((sum, value) => sum + value, 0)
  return exponentials.map((value) => value / total)
}

function temperatureScaledLogProbabilities(probabilities: number[], temperature: number) {
  if (!Number.isFinite(temperature) || temperature <= 0) {
    throw new Error('Ensemble temperature must be positive')
  }

  const values = probabilities.map((probability) => Math.log(Math.max(probability, EPSILON)) / temperature)
  const normalized = softmax(values)
  return normalized.map((probability) => Math.log(Math.max(probability, EPSILON)))
}

function calibratedLogits(
  modelProbabilities: number[][],
  config: CalibratedEnsembleConfig,
  labels: string[],
) {
  const classCount = labels.length
  const modelCount = config.modelPaths.length

  if (
    modelProbabilities.length !== modelCount ||
    config.temperatures.length !== modelCount ||
    config.theta.length !== modelCount ||
    config.bias.length !== classCount ||
    config.theta.some((row) => row.length !== classCount) ||
    modelProbabilities.some((row) => row.length !== classCount)
  ) {
    throw new Error('Ensemble configuration does not match its model outputs and labels')
  }

  const logProbabilities = modelProbabilities.map((probabilities, modelIndex) =>
    temperatureScaledLogProbabilities(probabilities, config.temperatures[modelIndex]!),
  )
  const activeBlend = labels.map((_, classIndex) => {
    const classWeights = softmax(config.theta.map((row) => row[classIndex]!))
    return classWeights.reduce(
      (sum, weight, modelIndex) => sum + weight * logProbabilities[modelIndex]![classIndex]!,
      0,
    )
  })
  return {
    activeBlend,
    logits: activeBlend.map((value, classIndex) => value + config.bias[classIndex]!),
  }
}

export function combineCalibratedProbabilities(
  modelProbabilities: number[][],
  config: CalibratedEnsembleConfig,
  labels: string[],
): ScoredClass[] {
  const probabilities = softmax(calibratedLogits(modelProbabilities, config, labels).logits)

  return probabilities.map((score, index) => ({ score, code: labels[index]! }))
}

export function combineCalibratedProbabilitiesWithClassSpecialist(
  modelProbabilities: number[][],
  config: CalibratedEnsembleConfig,
  labels: string[],
  specialistProbabilities: number[],
  targetCode: string,
  alpha = 1,
  specialistTemperature = 1,
): ScoredClass[] {
  const targetIndex = labels.indexOf(targetCode)
  if (targetIndex < 0 || specialistProbabilities.length !== labels.length) {
    throw new Error('Specialist output does not match its target class and labels')
  }
  if (!Number.isFinite(alpha) || alpha < 0 || alpha > 1) {
    throw new Error('Specialist alpha must be between zero and one')
  }

  const { activeBlend, logits } = calibratedLogits(modelProbabilities, config, labels)
  const specialistLogProbabilities = temperatureScaledLogProbabilities(
    specialistProbabilities,
    specialistTemperature,
  )
  logits[targetIndex] =
    (1 - alpha) * activeBlend[targetIndex]!
    + alpha * specialistLogProbabilities[targetIndex]!
    + config.bias[targetIndex]!
  const probabilities = softmax(logits)
  return probabilities.map((score, index) => ({ score, code: labels[index]! }))
}

export function validateCalibratedEnsembleConfig(value: unknown): CalibratedEnsembleConfig {
  if (!value || typeof value !== 'object') throw new Error('Ensemble configuration is malformed')
  const config = value as Partial<CalibratedEnsembleConfig>
  if (
    typeof config.version !== 'string' ||
    !Array.isArray(config.modelPaths) ||
    !config.modelPaths.every((path) => typeof path === 'string') ||
    !Array.isArray(config.temperatures) ||
    !config.temperatures.every(Number.isFinite) ||
    !Array.isArray(config.theta) ||
    !config.theta.every((row) => Array.isArray(row) && row.every(Number.isFinite)) ||
    !Array.isArray(config.bias) ||
    !config.bias.every(Number.isFinite)
  ) {
    throw new Error('Ensemble configuration is malformed')
  }
  return config as CalibratedEnsembleConfig
}
