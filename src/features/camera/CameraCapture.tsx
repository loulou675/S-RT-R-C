import { Camera, RotateCcw, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toAppError, type AppErrorCode } from '../../lib/errors'
import { preferredCameraSize } from '../../lib/deviceCapabilities'
import { measureFrameQuality } from './frameQuality'

interface CameraCaptureProps {
  onCapture: (dataUrl: string) => Promise<boolean>
  onCancel: () => void
  onError: (code: AppErrorCode) => void
}

const QUALITY_SAMPLE_SIZE = 64
const CAPTURE_SIZE = 640

type CaptureState = 'preview' | 'needs-retake' | 'processing'

interface CapturedFrame {
  dataUrl: string
  qualitySample: Uint8ClampedArray
}

export function CameraCapture({ onCapture, onCancel, onError }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const mountedRef = useRef(true)
  const [facingMode] = useState<'environment' | 'user'>(() =>
    window.matchMedia('(max-width: 860px)').matches ? 'environment' : 'user',
  )
  const [status, setStatus] = useState('Starting camera...')
  const [captureState, setCaptureState] = useState<CaptureState>('preview')
  const [capturedImage, setCapturedImage] = useState<string>()
  const isFrontCamera = facingMode === 'user'

  useEffect(() => {
    mountedRef.current = true
    let cancelled = false

    function stopCamera() {
      stopStream(streamRef)
    }

    async function startCamera() {
      setStatus('Starting camera...')
      setCaptureState('preview')
      setCapturedImage(undefined)

      if (!navigator.mediaDevices?.getUserMedia) {
        onError('CAMERA_NOT_AVAILABLE')
        return
      }

      try {
        stopCamera()
        const cameraSize = preferredCameraSize()
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: facingMode },
            width: { ideal: cameraSize.width },
            height: { ideal: cameraSize.height },
          },
          audio: false,
        })

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        streamRef.current = stream
        void enableContinuousFocus(stream)

        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
        }

        if (!cancelled) setStatus('Place one item inside the frame, then take a photo.')
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
    void startCamera()

    return () => {
      cancelled = true
      mountedRef.current = false
      window.removeEventListener('keydown', handleKeyDown)
      stopCamera()
    }
  }, [facingMode, onCancel, onError])

  async function handleCapture() {
    const video = videoRef.current
    if (captureState === 'processing') return

    if (captureState === 'needs-retake') {
      setCapturedImage(undefined)
      setCaptureState('preview')
      setStatus('Place one item inside the frame, then take a photo.')
      try {
        await video?.play()
      } catch {
        onError('CAMERA_NOT_AVAILABLE')
      }
      return
    }

    if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      onError('IMAGE_INVALID')
      return
    }

    const frame = captureFrame(video, isFrontCamera)
    if (!frame) {
      onError('IMAGE_INVALID')
      return
    }

    video.pause()
    setCapturedImage(frame.dataUrl)
    const quality = measureFrameQuality(frame.qualitySample, QUALITY_SAMPLE_SIZE)
    if (!quality.good) {
      setCaptureState('needs-retake')
      setStatus(`${quality.message} Retake the photo.`)
      return
    }

    setCaptureState('processing')
    setStatus('Identifying item...')
    stopStream(streamRef)
    const recognised = await onCapture(frame.dataUrl)
    if (!mountedRef.current) return

    if (!recognised) setStatus('No confident match. Opening the feedback form...')
  }

  return (
    <div className="camera-stage">
      <div className="camera-card" aria-live="polite">
        <div className={isFrontCamera ? 'camera-frame user-facing' : 'camera-frame'}>
          <video ref={videoRef} playsInline muted aria-label="Camera preview" />
          <div className="scan-shade" aria-hidden="true" />
          <div className={`scan-window ${captureState}`} aria-hidden="true">
            {capturedImage ? <img src={capturedImage} alt="" className="captured-scan-frame" /> : null}
          </div>
        </div>
      </div>
      <p className="status-line" role="status">{status}</p>
      <div className="camera-controls">
        <button type="button" className="camera-cancel-button" onClick={onCancel} aria-label="Close camera">
          <X size={20} aria-hidden="true" />
          <span>Cancel</span>
        </button>
        <button
          type="button"
          className={captureState === 'needs-retake' ? 'camera-retake-button' : 'camera-shutter-button'}
          onClick={() => void handleCapture()}
          disabled={captureState === 'processing'}
          aria-label={captureState === 'needs-retake' ? 'Retake photo' : 'Take photo'}
          title={captureState === 'needs-retake' ? 'Retake photo' : 'Take photo'}
        >
          {captureState === 'needs-retake'
            ? <><RotateCcw size={21} aria-hidden="true" /><span>Retake</span></>
            : <Camera size={25} aria-hidden="true" />}
        </button>
      </div>
    </div>
  )
}

function captureFrame(video: HTMLVideoElement, mirror: boolean): CapturedFrame | undefined {
  if (!video.videoWidth || !video.videoHeight) return undefined

  const canvas = document.createElement('canvas')
  canvas.width = CAPTURE_SIZE
  canvas.height = CAPTURE_SIZE
  const context = canvas.getContext('2d')
  if (!context) return undefined

  drawCenterCrop(context, video, CAPTURE_SIZE, mirror)

  const sampleCanvas = document.createElement('canvas')
  sampleCanvas.width = QUALITY_SAMPLE_SIZE
  sampleCanvas.height = QUALITY_SAMPLE_SIZE
  const sampleContext = sampleCanvas.getContext('2d', { willReadFrequently: true })
  if (!sampleContext) return undefined
  sampleContext.drawImage(canvas, 0, 0, QUALITY_SAMPLE_SIZE, QUALITY_SAMPLE_SIZE)

  return {
    dataUrl: canvas.toDataURL('image/jpeg', 0.9),
    qualitySample: sampleContext.getImageData(0, 0, QUALITY_SAMPLE_SIZE, QUALITY_SAMPLE_SIZE).data,
  }
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
  const cropDisplaySize = windowBounds?.width ?? Math.min(videoBounds.width, videoBounds.height) * 0.78
  const sourceSize = Math.min(cropDisplaySize / renderedScale, video.videoWidth, video.videoHeight)
  const sourceX = ((renderedWidth - videoBounds.width) / 2 + (videoBounds.width - cropDisplaySize) / 2) / renderedScale
  const sourceY = ((renderedHeight - videoBounds.height) / 2 + (videoBounds.height - cropDisplaySize) / 2) / renderedScale

  if (mirror) {
    context.translate(outputSize, 0)
    context.scale(-1, 1)
  }

  context.drawImage(video, sourceX, sourceY, sourceSize, sourceSize, 0, 0, outputSize, outputSize)
}

function stopStream(streamRef: { current: MediaStream | null }) {
  streamRef.current?.getTracks().forEach((track) => track.stop())
  streamRef.current = null
}

async function enableContinuousFocus(stream: MediaStream) {
  const track = stream.getVideoTracks()[0]
  if (!track?.getCapabilities) return

  try {
    const capabilities = track.getCapabilities() as MediaTrackCapabilities & { focusMode?: string[] }
    if (!capabilities.focusMode?.includes('continuous')) return
    await track.applyConstraints({
      advanced: [{ focusMode: 'continuous' } as MediaTrackConstraintSet],
    })
  } catch {
    // Browsers without camera focus controls keep their native autofocus.
  }
}
