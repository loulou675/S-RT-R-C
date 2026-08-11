import { describe, expect, it } from 'vitest'
import { AppError } from '../lib/errors'
import { evaluateDisposal, getDefaultConditionForItem } from '../features/sorting/ruleEngine'
import { trainingTargetClassCodes } from '../config/modelClasses'
import { wasteItems } from '../data/referenceData'
import type { ConditionKey } from '../types/domain'

function answers(condition: ConditionKey) {
  return {
    default: condition,
    container_state: condition,
    plastic_cup_condition: condition,
    container_condition: condition,
    plastic_cleanliness: condition,
    paper_condition: condition,
  }
}

function evaluate(itemCode: string, condition: ConditionKey = 'default') {
  return evaluateDisposal({
    siteCode: 'default_station',
    itemCode,
    conditionAnswers: answers(condition),
    locale: 'en',
  })
}

describe('rule engine', () => {
  it('selects the exact condition rule before a generic rule', () => {
    const result = evaluate('plastic_water_bottle', 'contains_liquid')

    expect(result.destinationBin.code).toBe('bottle_can')
    expect(result.componentActions.map((action) => action.destinationBin.code)).toEqual(['organic', 'bottle_can'])
  })

  it('routes a plastic bottle with liquid through component sorting', () => {
    const result = evaluate('plastic_water_bottle', 'contains_liquid')

    expect(result.mainInstruction).toContain('Pour out the remaining liquid')
    expect(result.preparationSteps).toContain('Pour remaining liquid into Organic Waste.')
  })

  it('routes a clean plastic cup to Clean Plastic', () => {
    const result = evaluate('plastic_takeaway_cup', 'clean_empty')

    expect(result.destinationBin.code).toBe('clean_plastic')
    expect(result.specialHandling).toBe(false)
  })

  it('routes a dirty plastic cup that cannot be cleaned to Landfill', () => {
    const result = evaluate('plastic_takeaway_cup', 'cannot_clean')

    expect(result.destinationBin.code).toBe('landfill')
    expect(result.warning).toContain('food-contaminated plastic')
  })

  it('routes a cleanable dirty plastic cup to Clean Plastic after rinsing', () => {
    const result = evaluate('plastic_takeaway_cup', 'empty_dirty_cleanable')

    expect(result.destinationBin.code).toBe('clean_plastic')
    expect(result.preparationSteps.join(' ')).toContain('Rinse')
  })

  it('routes a plastic food container with food through Organic and Clean Plastic', () => {
    const result = evaluate('plastic_food_container', 'contains_food_liquid')

    expect(result.destinationBin.code).toBe('clean_plastic')
    expect(result.componentActions.map((action) => action.destinationBin.code)).toEqual(['organic', 'clean_plastic'])
  })

  it('routes clean cardboard to Paper & Cardboard', () => {
    const result = evaluate('cardboard_box', 'clean_dry')

    expect(result.destinationBin.code).toBe('paper_cardboard')
  })

  it('routes greasy cardboard to Landfill', () => {
    const result = evaluate('cardboard_box', 'greasy')

    expect(result.destinationBin.code).toBe('landfill')
  })

  it('routes paper cups to Landfill with liquid separation', () => {
    const result = evaluate('paper_cup')

    expect(result.destinationBin.code).toBe('landfill')
    expect(result.componentActions.map((action) => action.destinationBin.code)).toEqual(['organic', 'landfill'])
  })

  it('routes food waste to Organic Waste', () => {
    const result = evaluate('food_waste')

    expect(result.destinationBin.code).toBe('organic')
  })

  it('keeps batteries out of the five normal bins', () => {
    const result = evaluate('battery')

    expect(result.destinationBin.code).toBe('special_handling')
    expect(result.specialHandling).toBe(true)
  })

  it('keeps broken glass out of the five normal bins', () => {
    const result = evaluate('broken_glass')

    expect(result.destinationBin.code).toBe('special_handling')
    expect(result.specialHandling).toBe(true)
  })

  it('filters reuse suggestions by required and prohibited conditions', () => {
    const clean = evaluate('cardboard_box', 'clean_dry')
    const greasy = evaluate('cardboard_box', 'greasy')

    expect(clean.reuseSuggestions.map((suggestion) => suggestion.code)).toContain('cardboard_storage')
    expect(greasy.reuseSuggestions).toHaveLength(0)
  })

  it('throws when no verified rule exists', () => {
    expect(() => evaluate('unknown')).toThrow(AppError)
  })

  it('returns a special-handling result with safe text only', () => {
    const result = evaluate('chemical_container')

    expect(result.specialHandling).toBe(true)
    expect(result.mainInstruction).toContain('Special handling')
    expect(result.preparationSteps.join(' ')).not.toContain('dismantle')
  })

  it('has a usable default rule for every active reference item', () => {
    const activeCodes = wasteItems.filter((item) => item.isActive && item.code !== 'unknown').map((item) => item.code)

    expect(() => activeCodes.forEach((itemCode) => evaluate(itemCode, getDefaultConditionForItem(itemCode)))).not.toThrow()
  })

  it('keeps every training class connected to an active reference item', () => {
    const activeCodes = new Set(wasteItems.filter((item) => item.isActive).map((item) => item.code))

    expect(trainingTargetClassCodes.filter((itemCode) => !activeCodes.has(itemCode))).toEqual([])
  })
})
