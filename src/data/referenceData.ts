import type {
  Bin,
  BinCode,
  ComponentAction,
  ConditionKey,
  ConditionQuestion,
  DisposalRule,
  Material,
  MaterialCode,
  ReuseSuggestion,
  SiteProfile,
  VerificationStatus,
  WasteItem,
} from '../types/domain'

const SIGNAGE: VerificationStatus = 'BASED_ON_LOCAL_GUIDANCE'
const PENDING: VerificationStatus = 'PENDING_CONFIRMATION'

export const siteProfiles: SiteProfile[] = [
  {
    code: 'default_station',
    nameVi: 'Trạm phân loại mẫu',
    nameEn: 'Default sorting station',
    country: 'Vietnam',
    city: 'Ho Chi Minh City',
    descriptionVi: 'Hướng dẫn phân loại rác cho trạm thùng rác đã chọn.',
    descriptionEn: 'Waste sorting guidance for the selected waste station.',
    isActive: true,
  },
]

export const bins: Bin[] = [
  {
    code: 'bottle_can',
    nameVi: 'Chai & Lon',
    nameEn: 'Bottle & Can',
    colorName: 'Orange',
    colorHex: '#cb795f',
    iconKey: 'bottle',
    descriptionVi: 'Chai nhựa rỗng, lon nhôm và chai được chấp nhận.',
    descriptionEn: 'Empty plastic drink bottles, aluminium cans and accepted bottles.',
    sortOrder: 1,
    isActive: true,
  },
  {
    code: 'organic',
    nameVi: 'Chất Thải Hữu Cơ',
    nameEn: 'Organic Waste',
    colorName: 'Green',
    colorHex: '#3e8860',
    iconKey: 'leaf',
    descriptionVi: 'Thức ăn thừa, vỏ trái cây và chất lỏng được chấp nhận.',
    descriptionEn: 'Leftover food, fruit peels and accepted liquids.',
    sortOrder: 2,
    isActive: true,
  },
  {
    code: 'clean_plastic',
    nameVi: 'Nhựa Sạch',
    nameEn: 'Clean Plastic',
    colorName: 'Red/Pink',
    colorHex: '#b43b44',
    iconKey: 'cup',
    descriptionVi: 'Ly nhựa sạch, hộp nhựa sạch, túi nhựa sạch và bao bì sạch.',
    descriptionEn: 'Clean plastic cups, containers, bags, snack packaging and clean foam.',
    sortOrder: 3,
    isActive: true,
  },
  {
    code: 'paper_cardboard',
    nameVi: 'Giấy & Bìa Carton',
    nameEn: 'Paper & Cardboard',
    colorName: 'Blue',
    colorHex: '#235398',
    iconKey: 'paper',
    descriptionVi: 'Giấy, túi giấy và bìa carton sạch, khô.',
    descriptionEn: 'Clean and dry paper, cardboard and paper bags.',
    sortOrder: 4,
    isActive: true,
  },
  {
    code: 'landfill',
    nameVi: 'Chất Thải Chôn Lấp',
    nameEn: 'Landfill',
    colorName: 'Brown',
    colorHex: '#793c36',
    iconKey: 'landfill',
    descriptionVi: 'Nhựa bẩn, ly giấy, khăn giấy và bao bì nhiễm bẩn.',
    descriptionEn: 'Dirty plastic, paper cups, tissues, napkins and contaminated packaging.',
    sortOrder: 5,
    isActive: true,
  },
  {
    code: 'special_handling',
    nameVi: 'Xử Lý Riêng',
    nameEn: 'Hazardous',
    colorName: 'Orange',
    colorHex: '#f4ca59',
    iconKey: 'alert',
    descriptionVi: 'Vật phẩm cần điểm thu gom được phê duyệt hoặc hướng dẫn từ nhân viên phụ trách.',
    descriptionEn: 'Items that need an approved collection point or guidance from responsible staff.',
    sortOrder: 6,
    isActive: true,
  },
]

export const materials: Material[] = [
  material('pet_plastic', 'Nhựa PET', 'PET plastic'),
  material('rigid_plastic', 'Nhựa cứng', 'Rigid plastic'),
  material('soft_plastic', 'Nhựa mềm', 'Soft plastic'),
  material('mixed_plastic', 'Nhựa hỗn hợp', 'Mixed plastic'),
  material('aluminium', 'Nhôm', 'Aluminium'),
  material('steel', 'Thép', 'Steel'),
  material('glass', 'Thủy tinh', 'Glass'),
  material('paper', 'Giấy', 'Paper'),
  material('cardboard', 'Bìa carton', 'Cardboard'),
  material('organic', 'Hữu cơ', 'Organic'),
  material('mixed_material', 'Vật liệu hỗn hợp', 'Mixed material'),
  material('wood', 'Gỗ', 'Wood'),
  material('electronic', 'Điện tử', 'Electronic'),
  material('hazardous', 'Nguy hại', 'Hazardous'),
  material('unknown', 'Chưa xác định', 'Unknown'),
]

export const wasteItems: WasteItem[] = [
  item('plastic_water_bottle', 'Chai nước nhựa', 'Plastic water bottle', 'pet_plastic', 'bottle', 'Bottle & Can', false, false, [
    'chai nhựa',
    'chai nước',
    'chai PET',
  ], ['water bottle', 'pet bottle', 'plastic drink bottle']),
  item('plastic_soft_drink_bottle', 'Chai nước ngọt nhựa', 'Plastic soft-drink bottle', 'pet_plastic', 'bottle', 'Bottle & Can', false, false, [
    'chai nước ngọt',
    'chai coca',
    'chai pepsi',
  ], ['soft drink bottle', 'soda bottle', 'plastic soda bottle']),
  item('aluminium_drink_can', 'Lon nước nhôm', 'Aluminium drink can', 'aluminium', 'can', 'Bottle & Can', false, false, [
    'lon nhôm',
    'lon nước',
    'lon coca',
  ], ['aluminium can', 'aluminum can', 'drink can']),
  item('steel_food_can', 'Lon thực phẩm thép', 'Steel food can', 'steel', 'can', 'Bottle & Can', false, false, [
    'lon đồ hộp',
    'hộp thiếc',
    'lon thép',
  ], ['steel can', 'food can', 'tin can']),
  item('glass_drink_bottle', 'Chai thủy tinh', 'Glass drink bottle', 'glass', 'bottle', 'Bottle & Can', false, false, [
    'chai thủy tinh',
    'chai bia',
    'chai nước thủy tinh',
  ], ['glass bottle', 'drink bottle', 'beer bottle']),
  item('plastic_takeaway_cup', 'Ly nhựa mang đi', 'Plastic takeaway cup', 'rigid_plastic', 'cup', 'Clean Plastic', false, false, [
    'ly nhựa',
    'cốc nhựa',
    'ly trà sữa',
  ], ['plastic cup', 'takeaway cup', 'iced drink cup']),
  item('plastic_cup_lid', 'Nắp ly nhựa', 'Plastic cup lid', 'rigid_plastic', 'lid', 'Clean Plastic', false, false, [
    'nắp ly',
    'nắp cốc',
    'nắp nhựa',
  ], ['plastic lid', 'cup lid', 'drink lid']),
  item('plastic_straw', 'Ống hút nhựa', 'Plastic straw', 'mixed_plastic', 'straw', 'Clean Plastic', false, false, [
    'ống hút',
    'ống hút nhựa',
  ], ['straw', 'plastic straw']),
  item('plastic_food_container', 'Hộp nhựa đựng thức ăn', 'Plastic food container', 'rigid_plastic', 'container', 'Clean Plastic', false, false, [
    'hộp nhựa',
    'hộp cơm nhựa',
    'hộp thức ăn',
  ], ['plastic food container', 'food container', 'takeaway container']),
  item('plastic_takeaway_box', 'Hộp nhựa mang đi', 'Plastic takeaway box', 'rigid_plastic', 'container', 'Clean Plastic', false, false, [
    'hộp mang đi',
    'hộp nhựa takeaway',
  ], ['plastic takeaway box', 'takeout box', 'takeaway box']),
  item('clean_plastic_bag', 'Túi nhựa sạch', 'Clean plastic bag', 'soft_plastic', 'bag', 'Clean Plastic', false, false, [
    'túi nhựa sạch',
    'bao ni lông sạch',
  ], ['clean plastic bag', 'clean bag', 'plastic bag clean']),
  item('dirty_plastic_bag', 'Túi nhựa bẩn', 'Dirty plastic bag', 'soft_plastic', 'bag', 'Landfill', false, false, [
    'túi nhựa bẩn',
    'bao ni lông bẩn',
  ], ['dirty plastic bag', 'contaminated bag']),
  item('snack_wrapper', 'Vỏ gói snack', 'Snack wrapper', 'mixed_plastic', 'wrapper', 'Clean Plastic', false, false, [
    'vỏ bánh',
    'bao bì snack',
    'vỏ snack',
  ], ['snack wrapper', 'chip bag', 'crisp packet']),
  item('instant_noodle_packaging', 'Bao bì mì ăn liền', 'Instant noodle packaging', 'mixed_plastic', 'wrapper', 'Clean Plastic', false, false, [
    'gói mì',
    'bao mì',
    'vỏ mì ăn liền',
  ], ['instant noodle packaging', 'noodle packet', 'ramen wrapper']),
  item('clean_styrofoam_container', 'Hộp xốp sạch', 'Clean styrofoam container', 'mixed_plastic', 'foam', 'Clean Plastic', false, false, [
    'hộp xốp sạch',
    'xốp sạch',
  ], ['clean styrofoam', 'clean foam container']),
  item('dirty_styrofoam_container', 'Hộp xốp bẩn', 'Dirty styrofoam container', 'mixed_plastic', 'foam', 'Landfill', false, false, [
    'hộp xốp bẩn',
    'xốp bẩn',
  ], ['dirty styrofoam', 'dirty foam container']),
  item('printing_paper', 'Giấy in', 'Printing paper', 'paper', 'paper', 'Paper & Cardboard', false, false, [
    'giấy in',
    'giấy a4',
  ], ['printing paper', 'copy paper', 'a4 paper']),
  item('notebook_paper', 'Giấy vở', 'Notebook paper', 'paper', 'paper', 'Paper & Cardboard', false, false, [
    'giấy vở',
    'vở cũ',
  ], ['notebook paper', 'loose leaf paper']),
  item('newspaper', 'Báo giấy', 'Newspaper', 'paper', 'paper', 'Paper & Cardboard', false, false, [
    'báo',
    'báo giấy',
  ], ['newspaper', 'newsprint']),
  item('magazine', 'Tạp chí', 'Magazine', 'paper', 'paper', 'Paper & Cardboard', false, false, [
    'tạp chí',
    'sách báo',
  ], ['magazine', 'catalogue']),
  item('paper_bag', 'Túi giấy', 'Paper bag', 'paper', 'bag', 'Paper & Cardboard', false, false, [
    'túi giấy',
    'bao giấy',
  ], ['paper bag', 'kraft bag']),
  item('cardboard_box', 'Thùng carton', 'Cardboard box', 'cardboard', 'box', 'Paper & Cardboard', false, false, [
    'thùng carton',
    'bìa carton',
    'hộp carton',
  ], ['cardboard box', 'carton box', 'box']),
  item('pizza_box', 'Hộp pizza', 'Pizza box', 'cardboard', 'box', 'Paper & Cardboard', false, false, [
    'hộp pizza',
    'hộp bánh pizza',
  ], ['pizza box', 'takeaway pizza box']),
  item('paper_cup', 'Ly giấy', 'Paper cup', 'mixed_material', 'cup', 'Landfill', false, false, [
    'ly giấy',
    'cốc giấy',
    'ly cà phê giấy',
  ], ['paper cup', 'takeaway coffee cup', 'coffee cup']),
  item('tissue', 'Khăn giấy', 'Tissue', 'paper', 'paper', 'Landfill', false, false, [
    'khăn giấy',
    'giấy lau',
  ], ['tissue', 'facial tissue']),
  item('paper_napkin', 'Khăn ăn giấy', 'Paper napkin', 'paper', 'paper', 'Landfill', false, false, [
    'khăn ăn',
    'khăn giấy ăn',
  ], ['paper napkin', 'napkin']),
  item('food_waste', 'Thức ăn thừa', 'Food waste', 'organic', 'food', 'Organic Waste', false, false, [
    'đồ ăn thừa',
    'thức ăn thừa',
  ], ['food waste', 'leftover food']),
  item('leftover_rice', 'Cơm thừa', 'Leftover rice', 'organic', 'food', 'Organic Waste', false, false, [
    'cơm thừa',
    'cơm dư',
  ], ['leftover rice', 'rice waste']),
  item('leftover_noodles', 'Mì thừa', 'Leftover noodles', 'organic', 'food', 'Organic Waste', false, false, [
    'mì thừa',
    'bún thừa',
    'phở thừa',
  ], ['leftover noodles', 'noodle waste']),
  item('fruit_peel', 'Vỏ trái cây', 'Fruit peel', 'organic', 'food', 'Organic Waste', false, false, [
    'vỏ trái cây',
    'vỏ chuối',
    'vỏ cam',
  ], ['fruit peel', 'banana peel', 'orange peel']),
  item('coffee_grounds', 'Bã cà phê', 'Coffee grounds', 'organic', 'food', 'Organic Waste', false, false, [
    'bã cà phê',
    'cặn cà phê',
  ], ['coffee grounds', 'coffee waste']),
  item('tea_bag', 'Túi trà', 'Tea bag', 'mixed_material', 'food', 'Organic Waste', false, false, [
    'túi trà',
    'bã trà',
  ], ['tea bag', 'used tea bag']),
  item('leftover_drink', 'Đồ uống thừa', 'Leftover drink', 'organic', 'liquid', 'Organic Waste', false, false, [
    'nước thừa',
    'đồ uống thừa',
  ], ['leftover drink', 'remaining liquid']),
  item('milk_tea_cup', 'Ly trà sữa', 'Milk tea cup', 'rigid_plastic', 'cup', 'Clean Plastic', false, false, [
    'trà sữa',
    'ly trà sữa',
  ], ['milk tea cup', 'bubble tea cup', 'boba cup']),
  item('plastic_spoon', 'Muỗng nhựa', 'Plastic spoon', 'mixed_plastic', 'utensil', 'Clean Plastic', false, false, [
    'muỗng nhựa',
    'thìa nhựa',
  ], ['plastic spoon', 'disposable spoon']),
  item('plastic_fork', 'Nĩa nhựa', 'Plastic fork', 'mixed_plastic', 'utensil', 'Clean Plastic', false, false, [
    'nĩa nhựa',
    'dĩa nhựa',
  ], ['plastic fork', 'disposable fork']),
  item('wooden_utensil', 'Dụng cụ gỗ dùng một lần', 'Wooden utensil', 'wood', 'utensil', 'Landfill', false, false, [
    'muỗng gỗ',
    'đũa gỗ',
    'dụng cụ gỗ',
  ], ['wooden utensil', 'wooden spoon', 'wooden fork']),
  item('battery', 'Pin', 'Battery', 'hazardous', 'battery', 'Special Handling', true, true, [
    'pin',
    'pin tiểu',
    'pin sạc',
  ], ['battery', 'aa battery', 'rechargeable battery']),
  item('mobile_phone', 'Điện thoại di động', 'Mobile phone', 'electronic', 'device', 'Special Handling', true, true, [
    'điện thoại',
    'điện thoại cũ',
  ], ['mobile phone', 'phone', 'smartphone']),
  item('electronic_cable', 'Dây cáp điện tử', 'Electronic cable', 'electronic', 'cable', 'Special Handling', true, true, [
    'dây cáp',
    'cáp sạc',
    'dây điện tử',
  ], ['electronic cable', 'charging cable', 'usb cable']),
  item('broken_glass', 'Thủy tinh vỡ', 'Broken glass', 'glass', 'glass', 'Special Handling', true, true, [
    'kính vỡ',
    'thủy tinh vỡ',
    'mảnh chai vỡ',
  ], ['broken glass', 'glass shard', 'shattered glass']),
  item('light_bulb', 'Bóng đèn', 'Light bulb', 'hazardous', 'bulb', 'Special Handling', true, true, [
    'bóng đèn',
    'đèn huỳnh quang',
  ], ['light bulb', 'fluorescent bulb', 'lamp bulb']),
  item('chemical_container', 'Bao bì hóa chất', 'Chemical container', 'hazardous', 'container', 'Special Handling', true, true, [
    'chai hóa chất',
    'hộp hóa chất',
    'bao bì hóa chất',
  ], ['chemical container', 'chemical bottle', 'hazard container']),
  item('medical_mask', 'Khẩu trang y tế', 'Medical mask', 'mixed_material', 'mask', 'Landfill', false, false, [
    'khẩu trang',
    'khẩu trang y tế',
  ], ['medical mask', 'face mask', 'disposable mask']),
  item('unknown', 'Vật phẩm chưa xác định', 'Unknown item', 'unknown', 'unknown', 'Unknown', false, false, [
    'không rõ',
    'vật lạ',
  ], ['unknown item', 'unknown waste']),
]

export const conditionQuestions: ConditionQuestion[] = [
  ...['plastic_water_bottle', 'plastic_soft_drink_bottle', 'aluminium_drink_can', 'glass_drink_bottle'].map(
    (itemCode) => ({
      itemCode,
      questionKey: 'container_state',
      questionVi: 'Vật phẩm có còn chất lỏng bên trong không?',
      questionEn: 'Does the item still contain liquid?',
      options: [
        option('empty', 'Không, đã rỗng', 'No, it is empty'),
        option('contains_liquid', 'Có, còn chất lỏng', 'Yes, it contains liquid'),
      ],
      sortOrder: 1,
      isActive: true,
    }),
  ),
  ...['plastic_takeaway_cup', 'milk_tea_cup'].map((itemCode) => ({
    itemCode,
    questionKey: 'plastic_cup_condition',
    questionVi: 'Ly đang ở tình trạng nào?',
    questionEn: 'What is the condition of the cup?',
    options: [
      option('clean_empty', 'Sạch và rỗng', 'Clean and empty'),
      option('contains_food_liquid', 'Còn thức ăn hoặc chất lỏng', 'Contains food or liquid'),
      option('empty_dirty_cleanable', 'Bẩn nhưng có thể rửa sạch', 'Empty but can be rinsed clean'),
      option('cannot_clean', 'Không thể làm sạch', 'Cannot be cleaned'),
    ],
    sortOrder: 1,
    isActive: true,
  })),
  ...['plastic_food_container', 'plastic_takeaway_box'].map((itemCode) => ({
    itemCode,
    questionKey: 'container_condition',
    questionVi: 'Hộp đang ở tình trạng nào?',
    questionEn: 'What is the condition of the container?',
    options: [
      option('clean_empty', 'Sạch và rỗng', 'Clean and empty'),
      option('contains_food_liquid', 'Còn thức ăn', 'Contains leftover food'),
      option('empty_dirty_cleanable', 'Bẩn nhưng có thể rửa sạch', 'Empty but can be cleaned'),
      option('cannot_clean', 'Không thể làm sạch', 'Cannot be cleaned'),
    ],
    sortOrder: 1,
    isActive: true,
  })),
  ...['plastic_cup_lid', 'plastic_straw', 'plastic_spoon', 'plastic_fork', 'snack_wrapper', 'instant_noodle_packaging', 'clean_styrofoam_container'].map(
    (itemCode) => ({
      itemCode,
      questionKey: 'plastic_cleanliness',
      questionVi: 'Vật phẩm có sạch và không còn thức ăn không?',
      questionEn: 'Is the item clean and free from food residue?',
      options: [
        option('clean', 'Sạch', 'Clean'),
        option('dirty', 'Bẩn hoặc dính thức ăn', 'Dirty or contaminated'),
      ],
      sortOrder: 1,
      isActive: true,
    }),
  ),
  ...[
    'printing_paper',
    'notebook_paper',
    'newspaper',
    'magazine',
    'paper_bag',
    'cardboard_box',
    'pizza_box',
  ].map((itemCode) => ({
    itemCode,
    questionKey: 'paper_condition',
    questionVi: 'Vật phẩm có sạch và khô không?',
    questionEn: 'Is the item clean and dry?',
    options: [
      option('clean_dry', 'Sạch và khô', 'Yes, clean and dry'),
      option('wet', 'Bị ướt', 'Wet'),
      option('greasy', 'Dính dầu mỡ hoặc bẩn', 'Greasy or contaminated'),
      option('partly_greasy', 'Chỉ bẩn một phần', 'Partly greasy'),
    ],
    sortOrder: 1,
    isActive: true,
  })),
]

const liquidFromContainer: ComponentAction[] = [
  component('Chất lỏng còn lại', 'Remaining liquid', 'organic'),
  component('Vỏ rỗng', 'Empty container', 'bottle_can'),
]

const foodFromPlastic: ComponentAction[] = [
  component('Thức ăn hoặc chất lỏng', 'Food or liquid', 'organic', {
    materialVi: 'Thức ăn / chất lỏng',
    materialEn: 'Food / liquid',
  }),
  component('Phần nhựa đã rửa sạch', 'Cleaned plastic item', 'clean_plastic', {
    materialVi: 'Nhựa',
    materialEn: 'Plastic',
  }),
]

const plasticCupComponents: ComponentAction[] = [
  component('Ly', 'Cup', 'clean_plastic', {
    materialVi: 'Nhựa',
    materialEn: 'Plastic',
    disposalNoteVi: 'Nhựa Sạch',
    disposalNoteEn: 'Clean Plastic',
  }),
  component('Nắp', 'Lid', 'clean_plastic', {
    materialVi: 'Nhựa',
    materialEn: 'Plastic',
    disposalNoteVi: 'Kiểm tra quy định tái chế tại điểm bỏ rác',
    disposalNoteEn: 'Check local recycling rules',
  }),
  component('Ống hút', 'Straw', 'landfill', {
    materialVi: 'Nhựa',
    materialEn: 'Plastic',
    disposalNoteVi: 'Chất Thải Chôn Lấp',
    disposalNoteEn: 'Landfill',
  }),
  component('Ống bọc giấy', 'Paper sleeve', 'paper_cardboard', {
    materialVi: 'Giấy',
    materialEn: 'Paper',
    disposalNoteVi: 'Giấy & Bìa Carton',
    disposalNoteEn: 'Paper & Cardboard',
  }),
]

const splitPizzaBox: ComponentAction[] = [
  component('Phần giấy sạch và khô', 'Clean and dry section', 'paper_cardboard'),
  component('Phần dính dầu mỡ', 'Greasy section', 'landfill'),
]

export const disposalRules: DisposalRule[] = [
  ...containerToBottleCanRules('plastic_water_bottle', 'chai nhựa', 'plastic bottle'),
  ...containerToBottleCanRules('plastic_soft_drink_bottle', 'chai nước ngọt', 'soft-drink bottle'),
  ...containerToBottleCanRules('aluminium_drink_can', 'lon nhôm', 'aluminium can'),
  ...containerToBottleCanRules('glass_drink_bottle', 'chai thủy tinh', 'glass bottle'),
  rule('steel_food_can', 'default', 'bottle_can', {
    vi: 'Làm rỗng lon, sau đó đặt vào thùng Chai & Lon.',
    en: 'Empty the can, then place it in Bottle & Can.',
    stepsVi: ['Đổ bỏ phần còn lại.', 'Làm sạch thức ăn bám nếu có thể.', 'Đặt lon vào Chai & Lon.'],
    stepsEn: ['Remove remaining contents.', 'Rinse food residue when possible.', 'Place the can in Bottle & Can.'],
  }),
  ...plasticCupRules('plastic_takeaway_cup', 'ly nhựa', 'plastic cup'),
  ...plasticCupRules('milk_tea_cup', 'ly trà sữa', 'milk tea cup'),
  ...plasticContainerRules('plastic_food_container', 'hộp nhựa', 'plastic food container'),
  ...plasticContainerRules('plastic_takeaway_box', 'hộp nhựa mang đi', 'plastic takeaway box'),
  ...cleanPlasticRules(['plastic_cup_lid', 'plastic_straw', 'plastic_spoon', 'plastic_fork']),
  ...cleanPlasticRules(['snack_wrapper', 'instant_noodle_packaging', 'clean_styrofoam_container']),
  rule('clean_plastic_bag', 'default', 'clean_plastic', {
    vi: 'Đặt túi nhựa sạch vào thùng Nhựa Sạch.',
    en: 'Place the clean plastic bag in Clean Plastic.',
    stepsVi: ['Lắc bỏ vụn thức ăn nếu có.', 'Đặt túi vào Nhựa Sạch.'],
    stepsEn: ['Shake out any crumbs.', 'Place the bag in Clean Plastic.'],
  }),
  rule('dirty_plastic_bag', 'default', 'landfill', {
    vi: 'Đặt túi nhựa bẩn vào thùng Chất Thải Chôn Lấp.',
    en: 'Place the dirty plastic bag in Landfill.',
    stepsVi: ['Không bỏ vào Nhựa Sạch nếu còn bẩn.', 'Đặt vào Chất Thải Chôn Lấp.'],
    stepsEn: ['Do not place it in Clean Plastic if contaminated.', 'Place it in Landfill.'],
    warningVi: 'Nếu túi có thể rửa sạch và làm khô, hãy dùng luồng tìm kiếm cho túi nhựa sạch.',
    warningEn: 'If the bag can be cleaned and dried, search for clean plastic bag instead.',
  }),
  rule('dirty_styrofoam_container', 'default', 'landfill', {
    vi: 'Đặt hộp xốp bẩn vào thùng Chất Thải Chôn Lấp.',
    en: 'Place the dirty styrofoam container in Landfill.',
    stepsVi: ['Đổ bỏ thức ăn còn lại.', 'Đặt hộp bẩn vào Chất Thải Chôn Lấp.'],
    stepsEn: ['Remove remaining food.', 'Place the dirty container in Landfill.'],
  }),
  ...paperRules([
    'printing_paper',
    'notebook_paper',
    'newspaper',
    'magazine',
    'paper_bag',
    'cardboard_box',
  ]),
  ...paperRules(['pizza_box'], true),
  rule('paper_cup', 'default', 'landfill', {
    vi: 'Đổ chất lỏng còn lại vào Hữu Cơ, sau đó bỏ ly giấy vào Chất Thải Chôn Lấp.',
    en: 'Empty remaining liquid into Organic Waste, then place the paper cup in Landfill.',
    stepsVi: ['Đổ chất lỏng còn lại.', 'Không bỏ ly giấy vào Giấy & Bìa Carton.', 'Đặt ly vào Chất Thải Chôn Lấp.'],
    stepsEn: ['Empty remaining liquid.', 'Do not place the cup in Paper & Cardboard.', 'Place the cup in Landfill.'],
    components: [
      component('Chất lỏng còn lại', 'Remaining liquid', 'organic'),
      component('Ly giấy', 'Paper cup', 'landfill'),
    ],
    warningVi: 'Ly giấy thường có lớp phủ và không thuộc nhóm giấy sạch.',
    warningEn: 'Paper cups usually have a lining and are not clean paper.',
  }),
  ...defaultRules(['tissue', 'paper_napkin', 'wooden_utensil', 'medical_mask'], 'landfill', {
    vi: 'Đặt vật phẩm này vào thùng Chất Thải Chôn Lấp.',
    en: 'Place this item in Landfill.',
    stepsVi: ['Không bỏ vào thùng tái chế.', 'Đặt vào Chất Thải Chôn Lấp.'],
    stepsEn: ['Do not place it in a recycling bin.', 'Place it in Landfill.'],
  }),
  ...defaultRules(
    ['food_waste', 'leftover_rice', 'leftover_noodles', 'fruit_peel', 'coffee_grounds', 'tea_bag', 'leftover_drink'],
    'organic',
    {
      vi: 'Đặt phần hữu cơ vào thùng Chất Thải Hữu Cơ.',
      en: 'Place the organic material in Organic Waste.',
      stepsVi: ['Tách bỏ bao bì không phải hữu cơ.', 'Đặt phần thức ăn hoặc chất lỏng vào Hữu Cơ.'],
      stepsEn: ['Remove any non-organic packaging.', 'Place the food or liquid in Organic Waste.'],
      warningVi: 'Bao bì đi kèm cần được phân loại riêng.',
      warningEn: 'Any packaging should be sorted separately.',
    },
  ),
  ...defaultRules(['battery', 'mobile_phone', 'electronic_cable', 'broken_glass', 'light_bulb', 'chemical_container'], 'special_handling', {
    vi: 'Vật phẩm này cần xử lý riêng.',
    en: 'Special handling is required for this item.',
    stepsVi: ['Không bỏ vào năm thùng rác thông thường.', 'Dùng điểm thu gom được phê duyệt hoặc hỏi nhân viên phụ trách.'],
    stepsEn: ['Do not place it in the five general waste bins.', 'Use an approved collection point or follow instructions from responsible staff.'],
    warningVi: 'Không cố tháo, đập vỡ hoặc xử lý sâu vật phẩm này.',
    warningEn: 'Do not dismantle, crush or attempt detailed handling of this item.',
  }),
]

export const reuseSuggestions: ReuseSuggestion[] = [
  reuse('plastic_bottle_planter', 'plastic_water_bottle', undefined, 'Chậu cây nhỏ', 'Reuse as a small planter', 'Cắt phần thân chai sạch để trồng cây nhỏ.', 'Use a clean bottle as a small planter.', ['empty', 'unbroken_clean'], ['dirty', 'cannot_clean'], [
    'Rửa sạch chai.',
    'Để khô hoàn toàn.',
    'Cắt phần thân khi có người lớn hoặc nhân viên hỗ trợ.',
    'Thêm đất và cây nhỏ.',
  ], [
    'Rinse the bottle.',
    'Let it dry fully.',
    'Cut the body only with appropriate help.',
    'Add soil and a small plant.',
  ]),
  reuse('plastic_bottle_storage', 'plastic_water_bottle', undefined, 'Hộp đựng vật liệu thủ công', 'Store craft materials', 'Dùng chai sạch để đựng hạt, kẹp giấy hoặc vật liệu thủ công.', 'Use a clean bottle to store beads, clips or craft material.', ['empty', 'unbroken_clean'], ['dirty', 'cannot_clean'], [
    'Rửa sạch và tháo nhãn nếu muốn.',
    'Để chai khô.',
    'Đậy nắp và dán nhãn nội dung.',
  ], [
    'Rinse the bottle and remove the label if useful.',
    'Let it dry.',
    'Close the cap and label the contents.',
  ]),
  reuse('cardboard_storage', 'cardboard_box', undefined, 'Hộp lưu trữ', 'Reuse for storage', 'Giữ thùng carton sạch để lưu tài liệu hoặc vật dụng nhẹ.', 'Keep a clean cardboard box for documents or lightweight items.', ['clean_dry'], ['wet', 'greasy'], [
    'Kiểm tra thùng khô và không mốc.',
    'Gấp lại nếu chưa dùng ngay.',
    'Dán nhãn khi dùng để lưu trữ.',
  ], [
    'Check that the box is dry and not mouldy.',
    'Flatten it if you are not using it now.',
    'Label it when used for storage.',
  ]),
  reuse('cardboard_packaging', 'cardboard_box', undefined, 'Đóng gói lại', 'Reuse for packaging', 'Dùng thùng sạch làm lớp bảo vệ khi vận chuyển đồ nhẹ.', 'Use a clean box as protective packaging for light items.', ['clean_dry'], ['wet', 'greasy'], [
    'Loại bỏ băng keo thừa.',
    'Kiểm tra độ chắc của thùng.',
    'Dùng giấy sạch để chèn đồ nếu cần.',
  ], [
    'Remove loose tape.',
    'Check that the box is sturdy.',
    'Use clean paper as padding if needed.',
  ]),
  reuse('glass_vase', 'glass_drink_bottle', undefined, 'Bình hoa nhỏ', 'Reuse as a flower vase', 'Chai thủy tinh sạch có thể dùng làm bình hoa nhỏ.', 'A clean glass bottle can become a small flower vase.', ['empty', 'unbroken_clean'], ['dirty'], [
    'Rửa sạch chai.',
    'Kiểm tra không có cạnh sắc hoặc nứt.',
    'Thêm nước và cắm hoa.',
  ], [
    'Wash the bottle.',
    'Check that it has no sharp edge or crack.',
    'Add water and flowers.',
  ]),
]

function material(code: MaterialCode, nameVi: string, nameEn: string): Material {
  return {
    code,
    nameVi,
    nameEn,
    descriptionVi: nameVi,
    descriptionEn: nameEn,
  }
}

function item(
  code: string,
  nameVi: string,
  nameEn: string,
  primaryMaterialCode: MaterialCode,
  objectType: string,
  category: string,
  hazardFlag: boolean,
  specialHandling: boolean,
  aliasesVi: string[],
  aliasesEn: string[],
): WasteItem {
  return {
    code,
    nameVi,
    nameEn,
    primaryMaterialCode,
    objectType,
    category,
    hazardFlag,
    specialHandling,
    imageKey: code,
    aliasesVi,
    aliasesEn,
    isActive: true,
    verificationStatus: code === 'unknown' ? PENDING : SIGNAGE,
  }
}

function option(value: ConditionKey, labelVi: string, labelEn: string) {
  return { value, labelVi, labelEn }
}

function component(
  componentVi: string,
  componentEn: string,
  destinationBinCode: BinCode,
  metadata: Pick<ComponentAction, 'materialVi' | 'materialEn' | 'disposalNoteVi' | 'disposalNoteEn'> = {},
): ComponentAction {
  return { componentVi, componentEn, destinationBinCode, ...metadata }
}

function rule(
  itemCode: string,
  conditionKey: ConditionKey,
  destinationBinCode: BinCode,
  text: {
    vi: string
    en: string
    stepsVi: string[]
    stepsEn: string[]
    warningVi?: string
    warningEn?: string
    whyVi?: string
    whyEn?: string
    components?: ComponentAction[]
  },
  priority = 100,
): DisposalRule {
  return {
    siteCode: 'default_station',
    itemCode,
    conditionKey,
    destinationBinCode,
    instructionShortVi: text.vi,
    instructionShortEn: text.en,
    instructionDetailedVi: text.vi,
    instructionDetailedEn: text.en,
    whyCategoryVi: text.whyVi ?? defaultWhyForBin(destinationBinCode, 'vi'),
    whyCategoryEn: text.whyEn ?? defaultWhyForBin(destinationBinCode, 'en'),
    preparationStepsVi: text.stepsVi,
    preparationStepsEn: text.stepsEn,
    warningVi: text.warningVi,
    warningEn: text.warningEn,
    componentActions: text.components ?? [],
    priority,
    verificationStatus: SIGNAGE,
    sourceReference: 'Local sorting guidance and MVP rule brief',
    isActive: true,
  }
}

function defaultWhyForBin(destinationBinCode: BinCode, locale: 'vi' | 'en') {
  const isVi = locale === 'vi'

  switch (destinationBinCode) {
    case 'bottle_can':
      return isVi
        ? 'Chai và lon rỗng thuộc nhóm Bottle & Can vì chúng có thể được thu gom riêng; chất lỏng còn lại cần được đổ bỏ để tránh nhiễm bẩn.'
        : 'Empty bottles and cans belong in Bottle & Can because they can be collected separately; remaining liquid should be removed to prevent contamination.'
    case 'organic':
      return isVi
        ? 'Thức ăn, vỏ trái cây và chất lỏng thuộc nhóm hữu cơ vì chúng cần được tách khỏi bao bì và vật liệu tái chế.'
        : 'Food scraps, fruit peels, and liquids belong in Organic Waste because they should be separated from packaging and recyclable materials.'
    case 'clean_plastic':
      return isVi
        ? 'Nhựa sạch có thể đi vào luồng Clean Plastic; thức ăn hoặc chất lỏng còn sót lại có thể làm bẩn cả nhóm tái chế.'
        : 'Clean plastic belongs in Clean Plastic because food or liquid residue can contaminate the recyclable plastic stream.'
    case 'paper_cardboard':
      return isVi
        ? 'Giấy và bìa chỉ phù hợp với Paper & Cardboard khi sạch và khô; nước, dầu mỡ hoặc thức ăn có thể làm hỏng luồng tái chế.'
        : 'Paper and cardboard belong here only when clean and dry; moisture, grease, or food residue can spoil the paper recycling stream.'
    case 'landfill':
      return isVi
        ? 'Vật phẩm này thuộc Landfill vì lớp phủ, chất bẩn hoặc vật liệu hỗn hợp khiến nó khó được xử lý trong các luồng tái chế tại điểm rác này.'
        : 'This item belongs in Landfill because lining, contamination, or mixed materials make it unsuitable for the recycling streams at this station.'
    case 'special_handling':
      return isVi
        ? 'Vật phẩm này cần xử lý riêng vì có thể gây rủi ro an toàn hoặc cần điểm thu gom được phê duyệt.'
        : 'This item needs special handling because it may create safety risks or require an approved collection point.'
  }
}

function containerToBottleCanRules(itemCode: string, viName: string, enName: string): DisposalRule[] {
  return [
    rule(itemCode, 'empty', 'bottle_can', {
      vi: `Đặt ${viName} rỗng vào thùng Chai & Lon.`,
      en: `Place the empty ${enName} in Bottle & Can.`,
      stepsVi: ['Đổ bỏ chất lỏng còn lại nếu có.', 'Đảm bảo vật phẩm rỗng.', 'Đặt vào Chai & Lon.'],
      stepsEn: ['Empty any remaining liquid.', 'Make sure the item is empty.', 'Place it in Bottle & Can.'],
    }),
    rule(itemCode, 'contains_liquid', 'bottle_can', {
      vi: `Đổ chất lỏng còn lại, sau đó đặt ${viName} rỗng vào Chai & Lon.`,
      en: `Pour out the remaining liquid, then place the empty ${enName} in Bottle & Can.`,
      stepsVi: ['Đổ chất lỏng còn lại vào Hữu Cơ.', 'Để vật phẩm rỗng.', 'Đặt vỏ rỗng vào Chai & Lon.'],
      stepsEn: ['Pour remaining liquid into Organic Waste.', 'Keep the container empty.', 'Place the empty container in Bottle & Can.'],
      components: liquidFromContainer,
    }),
  ]
}

function plasticCupRules(itemCode: string, viName: string, enName: string): DisposalRule[] {
  const cupWhyVi = 'Ly này được làm từ nhựa có thể tái chế, nhưng thức ăn hoặc chất lỏng còn sót lại có thể khiến vật phẩm không được tái chế.'
  const cupWhyEn = 'This cup is made from recyclable plastic, but food or liquid contamination may prevent it from being recycled.'
  const cupStepsVi = ['Đổ chất lỏng còn lại.', 'Rửa ly.', 'Tháo nắp và ống hút.', 'Để khô.', 'Đặt từng phần vào đúng thùng.']
  const cupStepsEn = ['Empty remaining liquid.', 'Rinse the cup.', 'Remove the lid and straw.', 'Let it dry.', 'Place each component in the correct bin.']

  return [
    rule(itemCode, 'clean_empty', 'clean_plastic', {
      vi: `Đặt ${viName} sạch và rỗng vào thùng Nhựa Sạch.`,
      en: `Place the clean and empty ${enName} in Clean Plastic.`,
      stepsVi: cupStepsVi,
      stepsEn: cupStepsEn,
      whyVi: cupWhyVi,
      whyEn: cupWhyEn,
      components: plasticCupComponents,
    }),
    rule(itemCode, 'contains_food_liquid', 'clean_plastic', {
      vi: `Đổ thức ăn hoặc chất lỏng, rửa ${viName}, rồi đặt vào Nhựa Sạch.`,
      en: `Empty food or liquid, rinse the ${enName}, then place it in Clean Plastic.`,
      stepsVi: cupStepsVi,
      stepsEn: cupStepsEn,
      whyVi: cupWhyVi,
      whyEn: cupWhyEn,
      components: [foodFromPlastic[0], ...plasticCupComponents],
    }),
    rule(itemCode, 'empty_dirty_cleanable', 'clean_plastic', {
      vi: `Rửa sạch ${viName}, để ráo, rồi đặt vào Nhựa Sạch.`,
      en: `Rinse the ${enName}, let it dry, then place it in Clean Plastic.`,
      stepsVi: cupStepsVi,
      stepsEn: cupStepsEn,
      whyVi: cupWhyVi,
      whyEn: cupWhyEn,
      components: plasticCupComponents,
    }),
    rule(itemCode, 'cannot_clean', 'landfill', {
      vi: `Nếu ${viName} không thể làm sạch, đặt vào Chất Thải Chôn Lấp.`,
      en: `If the ${enName} cannot be cleaned, place it in Landfill.`,
      stepsVi: ['Đổ bỏ chất lỏng hoặc thức ăn còn lại.', 'Đặt phần bẩn không thể làm sạch vào Chất Thải Chôn Lấp.'],
      stepsEn: ['Remove any remaining food or liquid.', 'Place the contaminated item in Landfill.'],
      whyVi: cupWhyVi,
      whyEn: cupWhyEn,
      warningVi: 'Nhựa còn dính dầu mỡ hoặc thức ăn không nên bỏ vào Nhựa Sạch.',
      warningEn: 'Greasy or food-contaminated plastic should not go in Clean Plastic.',
    }),
  ]
}

function plasticContainerRules(itemCode: string, viName: string, enName: string): DisposalRule[] {
  return [
    rule(itemCode, 'clean_empty', 'clean_plastic', {
      vi: `Đặt ${viName} sạch vào thùng Nhựa Sạch.`,
      en: `Place the clean ${enName} in Clean Plastic.`,
      stepsVi: ['Đảm bảo hộp không còn thức ăn.', 'Để khô nếu vừa rửa.', 'Đặt vào Nhựa Sạch.'],
      stepsEn: ['Make sure no food remains.', 'Let it dry if rinsed.', 'Place it in Clean Plastic.'],
    }),
    rule(itemCode, 'contains_food_liquid', 'clean_plastic', {
      vi: `Đổ thức ăn vào Hữu Cơ, rửa hộp, rồi đặt hộp sạch vào Nhựa Sạch.`,
      en: `Empty food into Organic Waste, rinse the container, then place the clean container in Clean Plastic.`,
      stepsVi: ['Đổ thức ăn còn lại vào Hữu Cơ.', 'Rửa hộp.', 'Để ráo.', 'Đặt hộp sạch vào Nhựa Sạch.'],
      stepsEn: ['Empty leftover food into Organic Waste.', 'Rinse the container.', 'Let it dry.', 'Place the clean container in Clean Plastic.'],
      components: foodFromPlastic,
    }),
    rule(itemCode, 'empty_dirty_cleanable', 'clean_plastic', {
      vi: `Rửa sạch ${viName}, để ráo, rồi đặt vào Nhựa Sạch.`,
      en: `Clean the ${enName}, let it dry, then place it in Clean Plastic.`,
      stepsVi: ['Rửa phần bẩn.', 'Để ráo.', 'Đặt vào Nhựa Sạch.'],
      stepsEn: ['Rinse the dirty area.', 'Let it dry.', 'Place it in Clean Plastic.'],
    }),
    rule(itemCode, 'cannot_clean', 'landfill', {
      vi: `Nếu ${viName} bị nhiễm bẩn nặng hoặc không thể làm sạch, đặt vào Chất Thải Chôn Lấp.`,
      en: `If the ${enName} is heavily contaminated or cannot be cleaned, place it in Landfill.`,
      stepsVi: ['Đổ bỏ thức ăn còn lại.', 'Đặt hộp bẩn vào Chất Thải Chôn Lấp.'],
      stepsEn: ['Remove leftover food.', 'Place the contaminated container in Landfill.'],
      warningVi: 'Chỉ bỏ nhựa vào Nhựa Sạch khi đã sạch.',
      warningEn: 'Only place plastic in Clean Plastic when it is clean.',
    }),
  ]
}

function cleanPlasticRules(itemCodes: string[]): DisposalRule[] {
  return itemCodes.flatMap((itemCode) => [
    rule(itemCode, 'clean', 'clean_plastic', {
      vi: 'Đặt vật phẩm nhựa sạch vào thùng Nhựa Sạch.',
      en: 'Place the clean plastic item in Clean Plastic.',
      stepsVi: ['Loại bỏ thức ăn hoặc chất lỏng nếu có.', 'Đảm bảo vật phẩm sạch.', 'Đặt vào Nhựa Sạch.'],
      stepsEn: ['Remove any food or liquid.', 'Make sure the item is clean.', 'Place it in Clean Plastic.'],
    }),
    rule(itemCode, 'dirty', 'landfill', {
      vi: 'Nếu vật phẩm nhựa còn bẩn hoặc dính thức ăn, đặt vào Chất Thải Chôn Lấp.',
      en: 'If the plastic item is dirty or food-contaminated, place it in Landfill.',
      stepsVi: ['Không bỏ vào Nhựa Sạch khi còn bẩn.', 'Đặt vào Chất Thải Chôn Lấp.'],
      stepsEn: ['Do not place it in Clean Plastic while contaminated.', 'Place it in Landfill.'],
      warningVi: 'Nếu có thể rửa sạch và làm khô, hãy chọn tình trạng sạch.',
      warningEn: 'If it can be rinsed and dried, choose the clean condition.',
    }),
  ])
}

function paperRules(itemCodes: string[], allowSplit = false): DisposalRule[] {
  return itemCodes.flatMap((itemCode) => [
    rule(itemCode, 'clean_dry', 'paper_cardboard', {
      vi: 'Đặt giấy hoặc bìa sạch, khô vào thùng Giấy & Bìa Carton.',
      en: 'Place clean and dry paper or cardboard in Paper & Cardboard.',
      stepsVi: ['Loại bỏ thức ăn hoặc chất lỏng.', 'Giữ vật phẩm sạch và khô.', 'Đặt vào Giấy & Bìa Carton.'],
      stepsEn: ['Remove food or liquid.', 'Keep the item clean and dry.', 'Place it in Paper & Cardboard.'],
    }),
    rule(itemCode, 'wet', 'landfill', {
      vi: 'Giấy hoặc bìa bị ướt nên đặt vào Chất Thải Chôn Lấp.',
      en: 'Wet paper or cardboard should go in Landfill.',
      stepsVi: ['Không bỏ giấy ướt vào thùng giấy sạch.', 'Đặt vào Chất Thải Chôn Lấp.'],
      stepsEn: ['Do not place wet paper in the clean paper bin.', 'Place it in Landfill.'],
      warningVi: 'Giấy ướt có thể làm nhiễm bẩn cả thùng tái chế.',
      warningEn: 'Wet paper can contaminate the recycling stream.',
    }),
    rule(itemCode, 'greasy', 'landfill', {
      vi: 'Giấy hoặc bìa dính dầu mỡ nên đặt vào Chất Thải Chôn Lấp.',
      en: 'Greasy or contaminated paper/cardboard should go in Landfill.',
      stepsVi: ['Không bỏ phần dính dầu mỡ vào Giấy & Bìa Carton.', 'Đặt vào Chất Thải Chôn Lấp.'],
      stepsEn: ['Do not place greasy material in Paper & Cardboard.', 'Place it in Landfill.'],
    }),
    ...(allowSplit
      ? [
          rule(itemCode, 'partly_greasy', 'paper_cardboard', {
            vi: 'Tách phần sạch vào Giấy & Bìa Carton và phần dính dầu mỡ vào Chất Thải Chôn Lấp.',
            en: 'Separate the clean section into Paper & Cardboard and the greasy section into Landfill.',
            stepsVi: ['Xé hoặc tách phần sạch.', 'Đặt phần sạch, khô vào Giấy & Bìa Carton.', 'Đặt phần dính dầu mỡ vào Chất Thải Chôn Lấp.'],
            stepsEn: ['Tear away the clean section.', 'Place clean and dry cardboard in Paper & Cardboard.', 'Place greasy cardboard in Landfill.'],
            components: splitPizzaBox,
          }),
        ]
      : [
          rule(itemCode, 'partly_greasy', 'landfill', {
            vi: 'Nếu không thể tách sạch phần bẩn, đặt vật phẩm vào Chất Thải Chôn Lấp.',
            en: 'If the contaminated section cannot be separated cleanly, place the item in Landfill.',
            stepsVi: ['Tách phần sạch nếu có thể.', 'Nếu không tách được, đặt vào Chất Thải Chôn Lấp.'],
            stepsEn: ['Separate the clean section if possible.', 'If not, place the item in Landfill.'],
            warningVi: 'Chỉ bỏ phần giấy sạch, khô vào Giấy & Bìa Carton.',
            warningEn: 'Only clean and dry paper should go in Paper & Cardboard.',
          }),
        ]),
  ])
}

function defaultRules(
  itemCodes: string[],
  destinationBinCode: BinCode,
  text: {
    vi: string
    en: string
    stepsVi: string[]
    stepsEn: string[]
    warningVi?: string
    warningEn?: string
  },
): DisposalRule[] {
  return itemCodes.map((itemCode) =>
    rule(itemCode, 'default', destinationBinCode, {
      vi: text.vi,
      en: text.en,
      stepsVi: text.stepsVi,
      stepsEn: text.stepsEn,
      warningVi: text.warningVi,
      warningEn: text.warningEn,
    }),
  )
}

function reuse(
  code: string,
  itemCode: string | undefined,
  materialCode: MaterialCode | undefined,
  titleVi: string,
  titleEn: string,
  summaryVi: string,
  summaryEn: string,
  requiredCondition: ConditionKey[] | undefined,
  prohibitedCondition: ConditionKey[] | undefined,
  stepsVi: string[],
  stepsEn: string[],
): ReuseSuggestion {
  return {
    code,
    itemCode,
    materialCode,
    titleVi,
    titleEn,
    summaryVi,
    summaryEn,
    requiredCondition,
    prohibitedCondition,
    stepsVi,
    stepsEn,
    safetyNoteVi: 'Chỉ tái sử dụng khi vật phẩm sạch, khô và không sắc nhọn.',
    safetyNoteEn: 'Reuse only when the item is clean, dry and not sharp.',
    difficulty: 'Easy',
    estimatedMinutes: 10,
    priority: 100,
    verificationStatus: PENDING,
    isActive: true,
  }
}
