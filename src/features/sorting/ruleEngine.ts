import { bins, conditionQuestions, disposalRules, reuseSuggestions, siteProfiles, wasteItems } from '../../data/referenceData'
import { AppError } from '../../lib/errors'
import type { ConditionKey, Locale, RuleEngineInput, RuleEngineResult } from '../../types/domain'

const acceptedRuleStatuses = new Set(['BASED_ON_LOCAL_GUIDANCE', 'VERIFIED_GUIDANCE'])

export function getItem(itemCode: string) {
  return wasteItems.find((item) => item.code === itemCode && item.isActive)
}

export function getBin(binCode: string) {
  return bins.find((bin) => bin.code === binCode && bin.isActive)
}

export function getQuestionForItem(itemCode: string) {
  return conditionQuestions.find((question) => question.itemCode === itemCode && question.isActive)
}

export function getDefaultConditionForItem(itemCode: string): ConditionKey {
  const question = getQuestionForItem(itemCode)
  return question?.options[0]?.value ?? 'default'
}

export function hasConditionQuestion(itemCode: string) {
  return Boolean(getQuestionForItem(itemCode))
}

export function evaluateDisposal(input: RuleEngineInput): RuleEngineResult {
  const locale: Locale = input.locale ?? 'en'
  const site = siteProfiles.find((profile) => profile.code === input.siteCode && profile.isActive)

  if (!site) {
    throw new AppError('DATABASE_UNAVAILABLE', `Unknown site: ${input.siteCode}`)
  }

  const item = getItem(input.itemCode)

  if (!item) {
    throw new AppError('ITEM_NOT_RECOGNISED', `Unknown item: ${input.itemCode}`)
  }

  const conditionKey = resolveConditionKey(item.code, input.conditionAnswers, input.detectedComponents)
  const selectedRule = disposalRules
    .filter((rule) => {
      const matchesItem = rule.itemCode === item.code
      const matchesSite = rule.siteCode === site.code
      const matchesCondition = rule.conditionKey === conditionKey || rule.conditionKey === 'default'
      const isVerified = acceptedRuleStatuses.has(rule.verificationStatus)
      return matchesItem && matchesSite && matchesCondition && rule.isActive && isVerified
    })
    .sort((left, right) => {
      const conditionPriority = Number(right.conditionKey === conditionKey) - Number(left.conditionKey === conditionKey)
      return conditionPriority || right.priority - left.priority
    })[0]

  if (!selectedRule) {
    throw new AppError('RULE_NOT_FOUND', `No verified rule exists for ${item.code}`)
  }

  const destinationBin = getBin(selectedRule.destinationBinCode)

  if (!destinationBin) {
    throw new AppError('RULE_NOT_FOUND', `Rule destination is missing for ${item.code}`)
  }

  const componentActions = selectedRule.componentActions.map((action) => {
    const destination = getBin(action.destinationBinCode)
    if (!destination) {
      throw new AppError('RULE_NOT_FOUND', `Component destination is missing for ${item.code}`)
    }
    return { ...action, destinationBin: destination }
  })

  const preparationSteps = locale === 'vi' ? selectedRule.preparationStepsVi : selectedRule.preparationStepsEn
  const preparationActions = preparationSteps.map((text, index) => {
    const codes = selectedRule.preparationComponentCodes[index] ?? []
    return {
      text,
      components: componentActions.filter((component) => codes.includes(component.code)),
    }
  })

  return {
    item,
    destinationBin,
    mainInstruction: locale === 'vi' ? selectedRule.instructionShortVi : selectedRule.instructionShortEn,
    detailedInstruction: locale === 'vi' ? selectedRule.instructionDetailedVi : selectedRule.instructionDetailedEn,
    whyCategory:
      (locale === 'vi' ? selectedRule.whyCategoryVi : selectedRule.whyCategoryEn) ??
      (locale === 'vi' ? selectedRule.instructionDetailedVi : selectedRule.instructionDetailedEn),
    preparationSteps,
    preparationActions,
    componentActions,
    warning: locale === 'vi' ? selectedRule.warningVi : selectedRule.warningEn,
    reuseSuggestions: filterReuseSuggestions(item.code, item.primaryMaterialCode, conditionKey).slice(0, 2),
    specialHandling: item.specialHandling || selectedRule.destinationBinCode === 'special_handling',
  }
}

function resolveConditionKey(
  itemCode: string,
  conditionAnswers: Record<string, ConditionKey>,
  detectedComponents?: RuleEngineInput['detectedComponents'],
): ConditionKey {
  const containsFood = detectedComponents?.some((component) => component.code === 'remaining_liquid')
  if (containsFood) {
    if (['plastic_takeaway_cup', 'milk_tea_cup', 'plastic_food_container', 'plastic_takeaway_box'].includes(itemCode)) {
      return 'contains_food_liquid'
    }
    if (['plastic_water_bottle', 'plastic_soft_drink_bottle', 'aluminium_drink_can', 'glass_drink_bottle'].includes(itemCode)) {
      return 'contains_liquid'
    }
  }

  const question = getQuestionForItem(itemCode)

  if (!question) {
    return conditionAnswers.default ?? 'default'
  }

  return conditionAnswers[question.questionKey] ?? question.options[0]?.value ?? 'default'
}

function filterReuseSuggestions(itemCode: string, materialCode: string, conditionKey: ConditionKey) {
  return reuseSuggestions
    .filter((suggestion) => {
      const matchesItem = suggestion.itemCode === itemCode
      const matchesMaterial = suggestion.materialCode === materialCode
      const matchesScope = matchesItem || matchesMaterial
      const required = suggestion.requiredCondition
      const prohibited = suggestion.prohibitedCondition
      const passesRequired = !required?.length || required.includes(conditionKey)
      const passesProhibited = !prohibited?.includes(conditionKey)
      return suggestion.isActive && matchesScope && passesRequired && passesProhibited
    })
    .sort((left, right) => right.priority - left.priority)
}
