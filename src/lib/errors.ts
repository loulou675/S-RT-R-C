export type AppErrorCode =
  | 'CAMERA_PERMISSION_DENIED'
  | 'CAMERA_NOT_AVAILABLE'
  | 'IMAGE_INVALID'
  | 'IMAGE_TOO_LARGE'
  | 'IMAGE_DECODE_FAILED'
  | 'MODEL_NOT_CONFIGURED'
  | 'MODEL_LOAD_FAILED'
  | 'INFERENCE_FAILED'
  | 'INFERENCE_TIMEOUT'
  | 'ITEM_NOT_RECOGNISED'
  | 'ITEM_AMBIGUOUS'
  | 'MULTIPLE_ITEMS_DETECTED'
  | 'DATABASE_UNAVAILABLE'
  | 'RULE_NOT_FOUND'
  | 'OFFLINE'

export class AppError extends Error {
  code: AppErrorCode

  constructor(code: AppErrorCode, message?: string, cause?: unknown) {
    super(message ?? code)
    this.name = 'AppError'
    this.code = code
    this.cause = cause
  }
}

export const retryMessage =
  'We could not clearly identify this item. Please place one item inside the frame and take another photo.'

export function messageForError(code?: AppErrorCode) {
  if (code === 'CAMERA_PERMISSION_DENIED') {
    return 'Camera access was blocked. You can upload an image or search manually.'
  }

  if (code === 'CAMERA_NOT_AVAILABLE') {
    return 'No camera was found on this device. You can upload an image or search manually.'
  }

  if (code === 'IMAGE_TOO_LARGE') {
    return 'This image is too large. Please choose a smaller JPG, PNG or WEBP image.'
  }

  if (code === 'IMAGE_INVALID' || code === 'IMAGE_DECODE_FAILED') {
    return 'This image could not be read. Please choose a JPG, PNG or WEBP image.'
  }

  if (code === 'DATABASE_UNAVAILABLE') {
    return 'Disposal guidance is temporarily unavailable. Please try manual search again.'
  }

  if (code === 'OFFLINE') {
    return 'You appear to be offline. Local scan guidance may be limited.'
  }

  return retryMessage
}

export function toAppError(error: unknown, fallback: AppErrorCode) {
  if (error instanceof AppError) {
    return error
  }

  return new AppError(fallback, fallback, error)
}
