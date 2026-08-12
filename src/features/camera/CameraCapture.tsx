import { useEffect, useRef, useState } from 'react'
import { toAppError, type AppErrorCode } from '../../lib/errors'

interface CameraCaptureProps {
  onCapture: (dataUrl: string) => Promise<boolean>
  onCancel: () => void
  onError: (code: AppErrorCode) => void
}

const SAMPLE_SIZE = 48
const STABLE_DIFFERENCE = 7.5
const REQUIRED_STABLE_SAMPLES = 2
const SCAN_SESSION_TIMEOUT_MS = 25_000
const MAX_FAILED_ATTEMPTS = 3
const DARK_LUMINANCE = 52
const GLARE_LUMINANCE = 222
const FAILURE_HINT_MS = 2_400

export function CameraCapture({ onCapture, onCancel, onError }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const previousSampleRef = useRef<Uint8ClampedArray | undefined>(undefined)
  const stableSamplesRef = useRef(0)
  const busyRef = useRef(false)
  const mountedRef = useRef(true)
  const scanStartedAtRef = useRef(0)
  const failedAttemptsRef = useRef(0)
  const failureHintUntilRef = useRef(0)
  const timeoutHandledRef = useRef(false)
  const [facingMode] = useState<'environment' | 'user'>(() =>
    window.matchMedia('(max-width: 860px)').matches ? 'environment' : 'user',
  )
  const [status, setStatus] = useState('Starting camera...')
  const isFrontCamera = facingMode === 'user'

  useEffect(() => {
    mountedRef.current = true
    let cancelled = false
    let sampleTimer: number | undefined

    function stopCamera() {
      if (sampleTimer) window.clearInterval(sampleTimer)
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }

    async function scanWhenStable() {
      const video = videoRef.current
      if (!video || timeoutHandledRef.current || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return

      const now = Date.now()
      const elapsed = now - scanStartedAtRef.current

      if (!busyRef.current && elapsed >= SCAN_SESSION_TIMEOUT_MS) {
        timeoutHandledRef.current = true
        onError('SCAN_TIMEOUT')
        return
      }

      if (busyRef.current || now < failureHintUntilRef.current) return

      const sample = sampleCenter(video)
      if (!sample) return

      const luminance = averageLuminance(sample)
      if (luminance < DARK_LUMINANCE) {
        stableSamplesRef.current = 0
        previousSampleRef.current = undefined
        setStatus('Too dark. Move to brighter, even light.')
        return
      }

      if (luminance > GLARE_LUMINANCE) {
        stableSamplesRef.current = 0
        previousSampleRef.current = undefined
        setStatus('Too much glare. Tilt the item or soften the light.')
        return
      }

      const previous = previousSampleRef.current
      previousSampleRef.current = sample

      if (!previous) {
        setStatus('Place one item inside the frame.')
        return
      }

      const difference = averagePixelDifference(previous, sample)
      stableSamplesRef.current = difference < STABLE_DIFFERENCE ? stableSamplesRef.current + 1 : 0
      setStatus(
        stableSamplesRef.current > 0
          ? 'Hold still. Scanning automatically...'
          : elapsed > 12_000
            ? 'Move one item closer and keep the background clear.'
            : 'Center one item and hold it still.',
      )

      if (stableSamplesRef.current < REQUIRED_STABLE_SAMPLES) return

      busyRef.current = true
      stableSamplesRef.current = 0
      setStatus('Identifying item...')

      const dataUrl = captureCenter(video, isFrontCamera)
      if (!dataUrl) {
        busyRef.current = false
        onError('IMAGE_INVALID')
        return
      }

      const recognised = await onCapture(dataUrl)
      if (!mountedRef.current) return

      if (!recognised) {
        previousSampleRef.current = undefined
        failedAttemptsRef.current += 1

        if (
          failedAttemptsRef.current >= MAX_FAILED_ATTEMPTS
          || Date.now() - scanStartedAtRef.current >= SCAN_SESSION_TIMEOUT_MS
        ) {
          timeoutHandledRef.current = true
          onError('SCAN_TIMEOUT')
          return
        }

        failureHintUntilRef.current = Date.now() + FAILURE_HINT_MS
        setStatus('Not clear yet. Add light, move closer, and show only one item.')
        window.setTimeout(() => {
          if (mountedRef.current) busyRef.current = false
        }, 900)
      }
    }

    async function startCamera() {
      setStatus('Starting camera...')

      if (!navigator.mediaDevices?.getUserMedia) {
        onError('CAMERA_NOT_AVAILABLE')
        return
      }

      try {
        stopCamera()
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: facingMode },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
          audio: false,
        })

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        streamRef.current = stream

        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
        }

        setStatus('Place one item inside the frame.')
        scanStartedAtRef.current = Date.now()
        failedAttemptsRef.current = 0
        failureHintUntilRef.current = 0
        timeoutHandledRef.current = false
        window.setTimeout(() => {
          if (!cancelled) sampleTimer = window.setInterval(scanWhenStable, 220)
        }, 350)
      } catch (error) {
        const appError = toAppError(
          error,
          error instanceof DOMException && error.name === 'NotAllowedError'
            ? 'CAMERA_PERMISSION_DENIED'
            : 'CAMERA_NOT_AVAILABLE',
        )
        onError(appError.code)
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onCancel()
    }

    window.addEventListener('keydown', handleKeyDown)
    startCamera()

    return () => {
      cancelled = true
      mountedRef.current = false
      window.removeEventListener('keydown', handleKeyDown)
      stopCamera()
    }
  }, [facingMode, isFrontCamera, onCancel, onCapture, onError])

  return (
    <div className="camera-stage">
      <div className="camera-card" aria-live="polite">
        <div className={isFrontCamera ? 'camera-frame user-facing' : 'camera-frame'}>
          <video ref={videoRef} playsInline muted aria-label="Camera preview" />
          <div className="scan-shade" aria-hidden="true" />
          <div className="scan-window" aria-hidden="true">
            <span />
          </div>
        </div>
      </div>
      <p className="status-line" role="status">{status}</p>
    </div>
  )
}

function sampleCenter(video: HTMLVideoElement) {
  const canvas = document.createElement('canvas')
  canvas.width = SAMPLE_SIZE
  canvas.height = SAMPLE_SIZE
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) return undefined

  drawCenterCrop(context, video, SAMPLE_SIZE, false)
  return context.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE).data
}

function captureCenter(video: HTMLVideoElement, mirror: boolean) {
  if (!video.videoWidth || !video.videoHeight) return undefined

  const outputSize = 640
  const canvas = document.createElement('canvas')
  canvas.width = outputSize
  canvas.height = outputSize
  const context = canvas.getContext('2d')
  if (!context) return undefined

  drawCenterCrop(context, video, outputSize, mirror)
  return canvas.toDataURL('image/jpeg', 0.9)
}

function drawCenterCrop(
  context: CanvasRenderingContext2D,
  video: HTMLVideoElement,
  outputSize: number,
  mirror: boolean,
) {
  const videoBounds = video.getBoundingClientRect()
  const windowBounds = video.parentElement?.querySelector('.scan-window')?.getBoundingClientRect()
  const renderedScale = Math.max(videoBounds.width / video.videoWidth, videoBounds.height / video.videoHeight)
  const renderedWidth = video.videoWidth * renderedScale
  const renderedHeight = video.videoHeight * renderedScale
  const cropDisplaySize = windowBounds?.width ?? Math.min(videoBounds.width, videoBounds.height) * 0.56
  const sourceSize = Math.min(cropDisplaySize / renderedScale, video.videoWidth, video.videoHeight)
  const sourceX = ((renderedWidth - videoBounds.width) / 2 + (videoBounds.width - cropDisplaySize) / 2) / renderedScale
  const sourceY = ((renderedHeight - videoBounds.height) / 2 + (videoBounds.height - cropDisplaySize) / 2) / renderedScale

  if (mirror) {
    context.translate(outputSize, 0)
    context.scale(-1, 1)
  }

  context.drawImage(video, sourceX, sourceY, sourceSize, sourceSize, 0, 0, outputSize, outputSize)
}

function averagePixelDifference(previous: Uint8ClampedArray, current: Uint8ClampedArray) {
  let difference = 0
  for (let index = 0; index < current.length; index += 4) {
    difference += Math.abs(current[index] - previous[index])
    difference += Math.abs(current[index + 1] - previous[index + 1])
    difference += Math.abs(current[index + 2] - previous[index + 2])
  }
  return difference / ((current.length / 4) * 3)
}

function averageLuminance(sample: Uint8ClampedArray) {
  let luminance = 0

  for (let index = 0; index < sample.length; index += 4) {
    luminance += sample[index] * 0.2126
    luminance += sample[index + 1] * 0.7152
    luminance += sample[index + 2] * 0.0722
  }

  return luminance / (sample.length / 4)
}
