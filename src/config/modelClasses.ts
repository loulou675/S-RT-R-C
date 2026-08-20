/** Visually distinct classes used by the browser classifier. */
export const trainingTargetClassCodes = [
  'aerosol_can',
  'aluminium_drink_can',
  'battery',
  'cardboard_box',
  'chemical_container',
  'dirty_plastic_bag',
  'disposable_diaper',
  'drink_carton',
  'electronic_cable',
  'food_waste',
  'fruit_peel',
  'glass_drink_bottle',
  'hair_clip',
  'hair_tie',
  'light_bulb',
  'medical_mask',
  'medicine_blister_pack',
  'mobile_phone',
  'newspaper',
  'paper_bag',
  'paper_cup',
  'paper_plate',
  'paperboard_packaging',
  'pen_marker',
  'phone_case',
  'plastic_bag',
  'plastic_cosmetic_container',
  'plastic_cup_lid',
  'plastic_food_container',
  'plastic_takeaway_cup',
  'plastic_water_bottle',
  'power_bank',
  'printing_paper',
  'sanitary_pad',
  'snack_wrapper',
  'steel_food_can',
  'styrofoam_container',
  'tissue',
  'unknown',
  'vegetable_scraps',
] as const

/** Classes currently present in public/models/waste_classifier.onnx. */
export const deployedModelClassCodes = trainingTargetClassCodes

// Backwards-compatible name used by the existing training feedback UI.
export const yoloClassCodes = deployedModelClassCodes
