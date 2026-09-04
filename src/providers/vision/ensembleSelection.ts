import { getClassifierBin, type ClassifierBinCode } from '../../config/classifierBins'

export interface ScoredClass {
  code: string
  score: number
}

export interface EnsembleSelection {
  itemCode: string
  itemScore: number
  itemMargin: number
  binCode: ClassifierBinCode
  binScore: number
  binMargin: number
}

export function selectEnsembledItem(
  itemClasses: ScoredClass[],
  binClasses: ScoredClass[],
  directBinWeight = 0.53,
): EnsembleSelection | undefined {
  const itemProbabilities = normalizeScores(itemClasses)
  const binProbabilities = normalizeScores(binClasses)
  const itemBinScores = new Map<ClassifierBinCode, number>()

  for (const item of itemProbabilities) {
    const binCode = getClassifierBin(item.code)
    if (!binCode) continue
    itemBinScores.set(binCode, (itemBinScores.get(binCode) ?? 0) + item.score)
  }

  const weight = Math.min(1, Math.max(0, directBinWeight))
  const rankedBins = binProbabilities
    .map(({ code, score }) => {
      const binCode = code as ClassifierBinCode
      return {
        code: binCode,
        score: weight * score + (1 - weight) * (itemBinScores.get(binCode) ?? 0),
      }
    })
    .sort((left, right) => right.score - left.score)

  const winningBin = rankedBins[0]
  if (!winningBin || winningBin.code === 'unknown') return undefined

  const rankedItems = itemProbabilities
    .filter((item) => getClassifierBin(item.code) === winningBin.code && item.code !== 'unknown')
    .sort((left, right) => right.score - left.score)
  const selectedItem = rankedItems[0]
  if (!selectedItem) return undefined

  return {
    itemCode: selectedItem.code,
    itemScore: selectedItem.score,
    itemMargin: selectedItem.score - (rankedItems[1]?.score ?? 0),
    binCode: winningBin.code,
    binScore: winningBin.score,
    binMargin: winningBin.score - (rankedBins[1]?.score ?? 0),
  }
}

function normalizeScores(classes: ScoredClass[]) {
  if (!classes.length) return []
  const finiteScores = classes.map(({ score }) => (Number.isFinite(score) ? score : 0))
  const sum = finiteScores.reduce((total, score) => total + score, 0)
  const alreadyProbabilities = finiteScores.every((score) => score >= 0 && score <= 1) && sum > 0.98 && sum < 1.02

  if (alreadyProbabilities) {
    return classes.map((entry, index) => ({ ...entry, score: finiteScores[index] ?? 0 }))
  }

  const maxScore = Math.max(...finiteScores)
  const exponentials = finiteScores.map((score) => Math.exp(score - maxScore))
  const exponentialSum = exponentials.reduce((total, score) => total + score, 0)
  return classes.map((entry, index) => ({ ...entry, score: (exponentials[index] ?? 0) / exponentialSum }))
}
