import { describe, expect, it } from 'vitest'
import { selectEnsembledItem } from '../providers/vision/ensembleSelection'

describe('selectEnsembledItem', () => {
  it('uses the bin classifier to rerank the item within the most likely bin', () => {
    const result = selectEnsembledItem(
      [
        { code: 'printing_paper', score: 0.45 },
        { code: 'plastic_water_bottle', score: 0.35 },
        { code: 'tissue', score: 0.2 },
      ],
      [
        { code: 'bottle_can', score: 0.9 },
        { code: 'paper_cardboard', score: 0.05 },
        { code: 'landfill', score: 0.03 },
        { code: 'clean_plastic', score: 0.01 },
        { code: 'hazardous', score: 0.005 },
        { code: 'organic', score: 0.003 },
        { code: 'unknown', score: 0.002 },
      ],
      0.49,
    )

    expect(result?.binCode).toBe('bottle_can')
    expect(result?.itemCode).toBe('plastic_water_bottle')
  })

  it('chooses the strongest item among classes in the winning bin', () => {
    const result = selectEnsembledItem(
      [
        { code: 'plastic_water_bottle', score: 0.25 },
        { code: 'aluminium_drink_can', score: 0.55 },
        { code: 'printing_paper', score: 0.2 },
      ],
      [
        { code: 'bottle_can', score: 0.8 },
        { code: 'paper_cardboard', score: 0.2 },
      ],
    )

    expect(result?.itemCode).toBe('aluminium_drink_can')
    expect(result?.itemMargin).toBeCloseTo(0.3)
  })

  it('abstains when the ensemble selects unknown', () => {
    const result = selectEnsembledItem(
      [
        { code: 'unknown', score: 0.8 },
        { code: 'printing_paper', score: 0.2 },
      ],
      [
        { code: 'unknown', score: 0.9 },
        { code: 'paper_cardboard', score: 0.1 },
      ],
    )

    expect(result).toBeUndefined()
  })
})

