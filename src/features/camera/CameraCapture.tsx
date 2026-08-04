import { Camera, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { AppError, toAppError, type AppErrorCode } from '../../lib/errors'

interface CameraCaptureProps {
  onCapture: (dataUrl: string) => void
  onCancel: () => void
  onError: (code: AppErrorCode) => void
}

export function CameraCapture({ onCapture, onCancel, onError }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [facingMode] = useState<'environment' | 'user'>(() =>
    window.matchMedia('(max-width: 860px)').matches ? 'environment' : 'user',
  )
  const [status, setStatus] = useState('Starting camera...')
  const isFrontCamera = facingMode === 'user'

  useEffect(() => {
    let cancelled = false

    function stopCamera() {
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
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

        setStatus('Place one item clearly inside the frame.')
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

    startCamera()

    return () => {
      cancelled = true
      stopCamera()
    }
  }, [facingMode, onError])

  function capture() {
    const video = videoRef.current

    if (!video || !video.videoWidth || !video.videoHeight) {
      throw new AppError('CAMERA_NOT_AVAILABLE', 'Video stream is unavailable')
    }

    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const context = canvas.getContext('2d')

    if (!context) {
      onError('IMAGE_INVALID')
      return
    }

    if (isFrontCamera) {
      context.translate(canvas.width, 0)
      context.scale(-1, 1)
    }

    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    onCapture(canvas.toDataURL('image/jpeg', 0.92))
  }

  return (
    <div className="camera-stage">
      <div className="camera-card" aria-live="polite">
        <div className={isFrontCamera ? 'camera-frame user-facing' : 'camera-frame'}>
          <video ref={videoRef} playsInline muted aria-label="Camera preview" />
          <div className="scan-haze" aria-hidden="true" />
          <div className="scan-window" aria-hidden="true" />
        </div>
      </div>
      <p className="status-line">{status}</p>
      <div className="button-row full">
        <button type="button" className="primary-action" onClick={capture}>
          <Camera size={17} aria-hidden="true" />
          Capture
        </button>
        <button type="button" className="secondary-action" onClick={onCancel}>
          <X size={17} aria-hidden="true" />
          Cancel
        </button>
      </div>
    </div>
  )
}
