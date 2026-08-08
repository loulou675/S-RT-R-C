import type { AppErrorCode } from '../lib/errors'
import type { InputMethod } from '../types/domain'

export interface TrainingFeedbackInput {
  imageDataUrl: string
  predictedItemCode?: string
  correctedItemCode: string
  inputMethod?: InputMethod
  errorCode?: AppErrorCode
  note?: string
}

export interface TrainingFeedbackRecord extends TrainingFeedbackInput {
  id: string
  createdAt: string
}

const storageKey = 'sot-rac-training-feedback-v1'
const maxRecords = 40

/**
 * Save a compact local copy so field-test feedback works without a backend.
 * The export can later be reviewed and added to the matching training class.
 */
export async function saveTrainingFeedback(input: TrainingFeedbackInput) {
  const record: TrainingFeedbackRecord = {
    ...input,
    imageDataUrl: await compactImage(input.imageDataUrl),
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
  }

  const records = readTrainingFeedback()
  localStorage.setItem(storageKey, JSON.stringify([record, ...records].slice(0, maxRecords)))
  return record
}

export function readTrainingFeedback(): TrainingFeedbackRecord[] {
  try {
    const stored = localStorage.getItem(storageKey)
    if (!stored) return []
    const parsed = JSON.parse(stored)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function downloadTrainingFeedback() {
  const records = readTrainingFeedback()
  const blob = new Blob([JSON.stringify(records, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  // Keep milliseconds in the filename so exports made on the same day remain
  // distinguishable when they are uploaded to the shared review folder.
  const exportTimestamp = new Date().toISOString().replace(/[:.]/g, '-')
  link.download = `sot-rac-training-feedback-${exportTimestamp}.json`
  link.click()
  URL.revokeObjectURL(url)
}

async function compactImage(source: string) {
  const image = new Image()
  image.src = source
  await image.decode()

  const maxSize = 640
  const scale = Math.min(1, maxSize / Math.max(image.naturalWidth, image.naturalHeight))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
  const context = canvas.getContext('2d')
  if (!context) return source

  context.drawImage(image, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.82)
}
