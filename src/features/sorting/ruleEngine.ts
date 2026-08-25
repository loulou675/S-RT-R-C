import { bins, conditionQuestions, disposalRules, reuseSuggestions, siteProfiles, wasteItems } from '../../data/referenceData'
import { AppError } from '../../lib/errors'
import type {
  BinCode,
  BroadMaterialCode,
  ConditionKey,
  Locale,
  MaterialCode,
  RuleEngineInput,
  RuleEngineResult,
} from '../../types/domain'

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

const materialFallbackGuidance: Record<BroadMaterialCode, {
  name: string
  materialCode: MaterialCode
  destinationBinCode: BinCode
  why: string
  steps: string[]
  warning?: string
}> = {
  plastic: {
    name: 'Likely plastic material',
    materialCode: 'mixed_plastic',
    destinationBinCode: 'clean_plastic',
    why: 'The exact item was not identified, but the material model detected plastic. At this station, plastic belongs in Clean Plastic only when it is empty and free of food or liquid.',
    steps: ['Remove food or liquid.', 'Rinse the plastic if needed.', 'Let it dry, then place it in Clean Plastic.'],
    warning: 'This is a material-only result. Search the exact item if it is dirty, multilayered, medical, or chemical packaging.',
  },
  metal: {
    name: 'Likely metal material',
    materialCode: 'steel',
    destinationBinCode: 'bottle_can',
    why: 'The exact item was not identified, but the material model detected metal. Empty metal packaging is handled with bottles and cans at this station.',
    steps: ['Make sure it is empty.', 'Remove food or liquid.', 'Place accepted metal packaging in Bottle & Can.'],
    warning: 'This is a material-only result. Search the exact item if it is sharp, pressurised, electronic, or not packaging.',
  },
  paper_cardboard: {
    name: 'Likely paper or cardboard',
    materialCode: 'paper',
    destinationBinCode: 'paper_cardboard',
    why: 'The exact item was not identified, but the material model detected paper or cardboard. This stream only accepts material that is clean and dry.',
    steps: ['Remove food or other contents.', 'Keep the material clean and dry.', 'Place it in Paper & Cardboard.'],
    warning: 'Wet, greasy, coated, or heavily contaminated paper may need a different destination.',
  },
  organic: {
    name: 'Likely organic material',
    materialCode: 'organic',
    destinationBinCode: 'organic',
    why: 'The exact item was not identified, but the material model detected food or plant-based organic material.',
    steps: ['Remove any packaging.', 'Keep non-food materials separate.', 'Place the organic material in Organic Waste.'],
  },
  glass: {
    name: 'Likely glass material',
    materialCode: 'glass',
    destinationBinCode: 'bottle_can',
    why: 'The exact item was not identified, but the material model detected glass. Accepted empty glass drink containers use the Bottle & Can stream at this station.',
    steps: ['Make sure it is empty.', 'Keep broken glass separate and ask staff.', 'Place accepted glass containers in Bottle & Can.'],
    warning: 'This is a material-only result. Do not use this bin for broken glass, bulbs, mirrors, or laboratory glass.',
  },
  electronic_battery: {
    name: 'Likely electronic or battery item',
    materialCode: 'electronic',
    destinationBinCode: 'special_handling',
    why: 'The exact item was not identified, but the material model detected an electronic or battery-like object that may require approved collection.',
    steps: ['Do not place it in a regular bin.', 'Keep damaged or swollen batteries away from heat.', 'Use an approved electronics or battery collection point.'],
    warning: 'Do not open, crush, puncture, or burn the item.',
  },
  landfill: {
    name: 'Likely general landfill item',
    materialCode: 'mixed_material',
    destinationBinCode: 'landfill',
    why: 'The exact item was approximate, but the reviewed destination router identified it as a general mixed-material household item for Landfill.',
    steps: ['Remove any battery or electronic part.', 'Keep liquids and recyclable parts separate.', 'Place the remaining item in Landfill.'],
    warning: 'This is a destination-level assumption. Use Special Handling instead if the item contains electronics, batteries, chemicals, or sharp hazardous parts.',
  },
  mixed_uncertain: {
    name: 'Mixed or uncertain material',
    materialCode: 'mixed_material',
    destinationBinCode: 'mixed_uncertain',
    why: 'The exact item and a reliable single material could not be identified, so the app is not choosing a disposal bin.',
    steps: ['Check the item label or packaging.', 'Search for the exact item in the app.', 'Ask staff before placing it in a recycling bin.'],
    warning: 'Do not guess based only on colour or appearance.',
  },
}

export function evaluateMaterialFallback(materialCode: BroadMaterialCode): RuleEngineResult {
  const guidance = materialFallbackGuidance[materialCode]
  const destinationBin = getBin(guidance.destinationBinCode)
  if (!destinationBin) throw new AppError('RULE_NOT_FOUND', `No material guidance exists for ${materialCode}`)

  const item = {
    code: `material_${materialCode}`,
    nameVi: guidance.name,
    nameEn: guidance.name,
    primaryMaterialCode: guidance.materialCode,
    objectType: 'material',
    category: 'Material-based result',
    hazardFlag: materialCode === 'electronic_battery',
    specialHandling: materialCode === 'electronic_battery',
    imageKey: `material_${materialCode}`,
    aliasesVi: [],
    aliasesEn: [],
    isActive: true,
    verificationStatus: 'PENDING_CONFIRMATION' as const,
  }
  const preparationActions = guidance.steps.map((text) => ({ text, components: [] }))

  return {
    item,
    destinationBin,
    mainInstruction: guidance.steps.at(-1) ?? guidance.why,
    detailedInstruction: guidance.why,
    whyCategory: guidance.why,
    preparationSteps: guidance.steps,
    preparationActions,
    componentActions: [],
    warning: guidance.warning,
    reuseSuggestions: [],
    specialHandling: materialCode === 'electronic_battery',
    matchLevel: 'material',
    materialCode,
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
