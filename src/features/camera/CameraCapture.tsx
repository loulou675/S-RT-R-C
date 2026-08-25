import { X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toAppError, type AppErrorCode } from '../../lib/errors'
import { averagePixelDifference, measureFrameQuality } from './frameQuality'
import { detectPrimaryObject, type ObjectDetection } from '../../providers/vision/objectDetector'

interface CameraCaptureProps {
  onCapture: (dataUrl: string) => Promise<boolean>
  onCancel: () => void
  onError: (code: AppErrorCode) => void
}

const SAMPLE_SIZE = 64
const SAMPLE_INTERVAL_MS = 220
const STARTUP_GRACE_MS = 1_800
const STABLE_DIFFERENCE = 4.8
const READY_STABLE_SAMPLES = 4
const CAPTURE_STABLE_SAMPLES = 7
const OBJECT_DETECTION_INTERVAL_MS = 720

type FocusState = 'adjusting' | 'ready' | 'scanning'
type DetectorState = 'warming' | 'searching' | 'found' | 'not-found'

export function CameraCapture({ onCapture, onCancel, onError }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const previousSampleRef = useRef<Uint8ClampedArray | undefined>(undefined)
  const stableSamplesRef = useRef(0)
  const busyRef = useRef(false)
  const detectionBusyRef = useRef(false)
  const lastDetectionAtRef = useRef(0)
  const detectionAttemptsRef = useRef(0)
  const objectDetectionRef = useRef<ObjectDetection | undefined>(undefined)
  const mountedRef = useRef(true)
  const [facingMode] = useState<'environment' | 'user'>(() =>
    window.matchMedia('(max-width: 860px)').matches ? 'environment' : 'user',
  )
  const [status, setStatus] = useState('Starting camera...')
  const [focusState, setFocusState] = useState<FocusState>('adjusting')
  const [objectDetection, setObjectDetection] = useState<ObjectDetection>()
  const [detectorState, setDetectorState] = useState<DetectorState>('warming')
  const isFrontCamera = facingMode === 'user'

  useEffect(() => {
    mountedRef.current = true
    let cancelled = false
    let sampleTimer: number | undefined
    let startupTimer: number | undefined

    function stopCamera() {
      if (sampleTimer) window.clearInterval(sampleTimer)
      if (startupTimer) window.clearTimeout(startupTimer)
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }

    function resetStability(sample?: Uint8ClampedArray) {
      stableSamplesRef.current = 0
      previousSampleRef.current = sample
      setFocusState('adjusting')
    }

    async function updateObjectDetection(video: HTMLVideoElement) {
      const now = performance.now()
      if (detectionBusyRef.current || now - lastDetectionAtRef.current < OBJECT_DETECTION_INTERVAL_MS) return

      const frame = captureCenter(video, isFrontCamera, 320)
      if (!frame) return
      detectionBusyRef.current = true
      lastDetectionAtRef.current = now
      setDetectorState('searching')
      try {
        const detection = await detectPrimaryObject(frame)
        detectionAttemptsRef.current += 1
        objectDetectionRef.current = detection
        if (!cancelled && mountedRef.current) {
          setObjectDetection(detection)
          setDetectorState(detection ? 'found' : 'not-found')
        }
      } catch {
        detectionAttemptsRef.current += 1
        objectDetectionRef.current = undefined
        if (!cancelled && mountedRef.current) {
          setObjectDetection(undefined)
          setDetectorState('not-found')
        }
      } finally {
        detectionBusyRef.current = false
      }
    }

    async function scanWhenReady() {
      const video = videoRef.current
      if (busyRef.current || !video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return

      const sample = sampleCenter(video)
      if (!sample) return

      const quality = measureFrameQuality(sample, SAMPLE_SIZE)
      if (!quality.good) {
        resetStability(sample)
        setStatus(quality.message)
        return
      }


      void updateObjectDetection(video)

      const previous = previousSampleRef.current
      previousSampleRef.current = sample
      if (!previous) {
        setStatus('Center one item in the yellow square and hold still.')
        return
      }

      const difference = averagePixelDifference(previous, sample)
      stableSamplesRef.current = difference <= STABLE_DIFFERENCE ? stableSamplesRef.current + 1 : 0

      if (stableSamplesRef.current < READY_STABLE_SAMPLES) {
        setFocusState('adjusting')
        setStatus(difference <= STABLE_DIFFERENCE ? 'Hold still while focus settles.' : 'Keep one item centered and hold still.')
        return
      }

      setFocusState('ready')
      if (!objectDetectionRef.current && detectionAttemptsRef.current < 2) {
        setStatus('Position is good. Hold still while YOLO checks the object...')
        return
      }
      setStatus(
        objectDetectionRef.current
          ? 'Object detected. Hold still—scanning automatically...'
          : 'No YOLO box found. Using the full focus square...',
      )
      if (stableSamplesRef.current < CAPTURE_STABLE_SAMPLES) return

      const dataUrl = captureCenter(video, isFrontCamera)
      if (!dataUrl) {
        resetStability()
        onError('IMAGE_INVALID')
        return
      }

      busyRef.current = true
      stableSamplesRef.current = 0
      setFocusState('scanning')
      setStatus('Identifying item...')
      const recognised = await onCapture(dataUrl)
      if (!mountedRef.current) return

      if (!recognised) {
        setFocusState('adjusting')
        setStatus('No confident match. Opening the feedback form...')
      }
    }

    async function startCamera() {
      setStatus('Starting camera...')
      setFocusState('adjusting')
      busyRef.current = false
      detectionBusyRef.current = false
      lastDetectionAtRef.current = 0
      detectionAttemptsRef.current = 0
      objectDetectionRef.current = undefined
      previousSampleRef.current = undefined
      stableSamplesRef.current = 0
      setObjectDetection(undefined)
      setDetectorState('warming')

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

        if (!cancelled) {
          setStatus('Place one item inside the yellow square.')
          startupTimer = window.setTimeout(() => {
            if (!cancelled) sampleTimer = window.setInterval(() => void scanWhenReady(), SAMPLE_INTERVAL_MS)
          }, STARTUP_GRACE_MS)
        }
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
          <div className={`scan-window ${focusState}`} aria-hidden="true">
            <span />
            {objectDetection ? (
              <i
                className="detected-object-box"
                style={{
                  left: `${objectDetection.x * 100}%`,
                  top: `${objectDetection.y * 100}%`,
                  width: `${objectDetection.width * 100}%`,
                  height: `${objectDetection.height * 100}%`,
                }}
              />
            ) : null}
          </div>
          <div className={`live-detector-status ${detectorState}`} aria-live="polite">
            <strong>YOLO</strong>
            <span>
              {detectorState === 'found' && objectDetection
                ? `Object box ${Math.round(objectDetection.confidence * 100)}%`
                : detectorState === 'not-found'
                  ? 'No reliable box'
                  : detectorState === 'searching'
                    ? 'Checking object...'
                    : 'Warming up...'}
            </span>
          </div>
        </div>
      </div>
      <p className="status-line" role="status">{status}</p>
      <div className="camera-controls">
        <button type="button" className="camera-cancel-button" onClick={onCancel} aria-label="Close camera">
          <X size={20} aria-hidden="true" />
          <span>Cancel</span>
        </button>
      </div>
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

function captureCenter(video: HTMLVideoElement, mirror: boolean, outputSize = 640) {
  if (!video.videoWidth || !video.videoHeight) return undefined

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
