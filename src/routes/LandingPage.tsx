import { ImageUp, ScanLine, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BinPanel } from '../components/BinPanel'
import { StatusBlock } from '../components/StatusBlock'
import { TrainingFeedbackPanel } from '../components/TrainingFeedbackPanel'
import { UserSurveyModal } from '../components/UserSurveyModal'
import { CameraCapture } from '../features/camera/CameraCapture'
import { isEmbeddedSocialBrowser } from '../features/camera/browserSupport'
import { fileToDataUrl } from '../features/camera/fileInput'
import { evaluateDisposal, evaluateMaterialFallback, getDefaultConditionForItem } from '../features/sorting/ruleEngine'
import { AppError, messageForError, messageForErrorVi, toAppError } from '../lib/errors'
import { maxImageMegabytes } from '../lib/validation/imageValidation'
import { createVisionProvider, resetVisionProvider } from '../providers/vision'
import {
  focusPrimaryObject,
  isSafeRescueDetection,
  type ObjectDetection,
} from '../providers/vision/objectDetector'
import { saveScanHistory } from '../services/history'
import { trackFeature } from '../services/siteAnalytics'
import type { AppErrorCode } from '../lib/errors'
import type { BroadMaterialCode, DetectedComponent, InputMethod, RuleEngineResult } from '../types/domain'

type RecognitionStage = 'idle' | 'camera' | 'processing'

interface SurveyContext {
  inputMethod: InputMethod
  predictedItemCode?: string
  destinationBinCode?: string
}

interface PendingSurvey {
  after: 'result-delay' | 'feedback-submit'
  context: SurveyContext
}

interface DetectorDebugState {
  image: string
  detection?: ObjectDetection
}

// Bump this when the survey UI changes so an existing browser session can see the new version once.
const surveySessionKey = 'sot-rac-post-scan-survey-v3-shown'
const surveyResultDelayMs = Number(import.meta.env.VITE_SURVEY_DELAY_MS ?? 12_000)
let surveySessionFallbackShown = false

function markSurveyShownForSession() {
  try {
    if (window.sessionStorage.getItem(surveySessionKey)) return false
    window.sessionStorage.setItem(surveySessionKey, 'true')
    return true
  } catch {
    if (surveySessionFallbackShown) return false
    surveySessionFallbackShown = true
    return true
  }
}

export function LandingPage() {
  const [searchParams] = useSearchParams()
  const [stage, setStage] = useState<RecognitionStage>('idle')
  const [imagePreview, setImagePreview] = useState<string>()
  const [inputMethod, setInputMethod] = useState<InputMethod>('camera')
  const [result, setResult] = useState<RuleEngineResult>()
  const [predictedItemCode, setPredictedItemCode] = useState<string>()
  const [status, setStatus] = useState<string>()
  const [errorCode, setErrorCode] = useState<AppErrorCode>()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [resultCollapsed, setResultCollapsed] = useState(false)
  const [feedbackDelivery, setFeedbackDelivery] = useState<'uploaded' | 'queued'>()
  const [surveyOpen, setSurveyOpen] = useState(false)
  const [surveyContext, setSurveyContext] = useState<SurveyContext>()
  const [detectorDebug, setDetectorDebug] = useState<DetectorDebugState>()
  const recognitionIdRef = useRef(0)
  const pendingSurveyRef = useRef<PendingSurvey | undefined>(undefined)
  const surveyTimerRef = useRef<number | undefined>(undefined)
  const feedbackSectionRef = useRef<HTMLDivElement | null>(null)
  const searchedItemCode = searchParams.get('item')
  const searchedMaterialCode = searchParams.get('material') as BroadMaterialCode | null
  const searchedSource = searchParams.get('source')
  const previewMode = searchParams.get('preview')

  useEffect(() => {
    const prepareModel = () => {
      void createVisionProvider().then((provider) => provider.prepare?.()).catch(() => undefined)
    }
    const idleId = window.setTimeout(prepareModel, 150)
    return () => window.clearTimeout(idleId)
  }, [])

  useEffect(() => () => {
    if (surveyTimerRef.current !== undefined) window.clearTimeout(surveyTimerRef.current)
  }, [])

  useEffect(() => {
    if (!searchedItemCode && !searchedMaterialCode) return

    try {
      const disposal = searchedMaterialCode
        ? evaluateMaterialFallback(searchedMaterialCode)
        : getDisposalForItem(searchedItemCode as string)
      setResult(disposal)
      setResultCollapsed(false)
      setErrorCode(undefined)
      setStage('idle')
      setStatus(undefined)
      if (searchedSource !== 'history') {
        saveScanHistory(disposal, 'manual')
      }
    } catch (error) {
      const appError = error instanceof AppError ? error : toAppError(error, 'RULE_NOT_FOUND')
      setErrorCode(appError.code)
    }
  }, [searchedItemCode, searchedMaterialCode, searchedSource])

  useEffect(() => {
    if (!import.meta.env.DEV || previewMode !== 'survey') return
    setSurveyContext({
      inputMethod: 'camera',
      predictedItemCode: 'plastic_water_bottle',
      destinationBinCode: 'bottle_can',
    })
    setSurveyOpen(true)
  }, [previewMode])

  useEffect(() => {
    if (stage !== 'idle' || !errorCode || !imagePreview) return

    const frame = window.requestAnimationFrame(() => {
      feedbackSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [errorCode, imagePreview, stage])

  function openPendingSurvey(after: PendingSurvey['after'], context?: SurveyContext) {
    const pending = pendingSurveyRef.current
    if (!pending || pending.after !== after) return

    pendingSurveyRef.current = undefined
    if (!markSurveyShownForSession()) return
    setSurveyContext(context ?? pending.context)
    setSurveyOpen(true)
  }

  function clearPendingResultSurvey() {
    if (surveyTimerRef.current !== undefined) {
      window.clearTimeout(surveyTimerRef.current)
      surveyTimerRef.current = undefined
    }
    if (pendingSurveyRef.current?.after === 'result-delay') {
      pendingSurveyRef.current = undefined
    }
  }

  function scheduleResultSurvey(context: SurveyContext) {
    clearPendingResultSurvey()
    pendingSurveyRef.current = { after: 'result-delay', context }
    surveyTimerRef.current = window.setTimeout(() => {
      surveyTimerRef.current = undefined
      openPendingSurvey('result-delay')
    }, surveyResultDelayMs)
  }

  function closeResult() {
    clearPendingResultSurvey()
    recognitionIdRef.current += 1
    setResult(undefined)
    setResultCollapsed(false)
    setErrorCode(undefined)
  }

  function startCamera() {
    void trackFeature('camera_scan')
    closeResult()
    setFeedbackDelivery(undefined)
    setImagePreview(undefined)
    setPredictedItemCode(undefined)
    setDetectorDebug(undefined)
    setInputMethod('camera')
    if (isEmbeddedSocialBrowser()) {
      setErrorCode('CAMERA_EMBEDDED_BROWSER')
      setStage('idle')
      return
    }
    setStage('camera')
  }

  function openUpload() {
    void trackFeature('image_upload')
    closeResult()
    setFeedbackDelivery(undefined)
    setImagePreview(undefined)
    setPredictedItemCode(undefined)
    setDetectorDebug(undefined)
    setUploadOpen(true)
  }

  const recogniseImage = useCallback(async (dataUrl: string, method: InputMethod, keepCameraOpen = false) => {
    const recognitionId = recognitionIdRef.current + 1
    recognitionIdRef.current = recognitionId
    if (surveyTimerRef.current !== undefined) {
      window.clearTimeout(surveyTimerRef.current)
      surveyTimerRef.current = undefined
    }
    pendingSurveyRef.current = undefined
    setFeedbackDelivery(undefined)
    setImagePreview(dataUrl)
    if (import.meta.env.VITE_OBJECT_DETECTOR_DEBUG === 'true') {
      setDetectorDebug({ image: dataUrl })
    }
    setInputMethod(method)
    setErrorCode(undefined)
    if (!keepCameraOpen) setStage('processing')

    try {
      setStatus('Identifying item... The first scan may take a little longer.')
      let provider = await createVisionProvider()
      let inferenceImage = dataUrl
      let visionResult
      try {
        // The indicator-square image is authoritative. A generic detector may
        // find a useful object box, but it must not replace a successful scan.
        visionResult = await provider.identify(dataUrl)
      } catch (originalError) {
        const appError = originalError instanceof AppError
          ? originalError
          : toAppError(originalError, 'INFERENCE_FAILED')
        if (appError.code === 'MODEL_LOAD_FAILED') {
          setStatus('Retrying the AI model...')
          resetVisionProvider()
          provider = await createVisionProvider()
          visionResult = await provider.identify(dataUrl)
        } else {
          const eligibleError = ['ITEM_NOT_RECOGNISED', 'ITEM_AMBIGUOUS', 'MATERIAL_NOT_RECOGNISED']
            .includes(appError.code)
          if (!eligibleError) throw originalError

          setStatus('Checking the object framing...')
          let focused
          try {
            focused = await focusPrimaryObject(dataUrl)
            if (recognitionId !== recognitionIdRef.current) return false
            if (import.meta.env.VITE_OBJECT_DETECTOR_DEBUG === 'true') {
              setDetectorDebug({ image: dataUrl, detection: focused.detection })
            }
          } catch (error) {
            if (import.meta.env.DEV) console.warn('Object-focused retry was skipped.', error)
            throw originalError
          }

          const rescueConfidence = Number(import.meta.env.VITE_OBJECT_DETECTOR_RESCUE_MIN_CONFIDENCE ?? 0.70)
          const rescueArea = Number(import.meta.env.VITE_OBJECT_DETECTOR_RESCUE_MIN_AREA ?? 0.10)
          const detectedArea = focused.detection ? focused.detection.width * focused.detection.height : 0
          const canRescue = Boolean(focused.detection)
            && focused.detection!.confidence >= rescueConfidence
            && detectedArea >= rescueArea
            && isSafeRescueDetection(focused.detection!)
            && focused.image !== dataUrl

          if (!canRescue) throw originalError

          try {
            inferenceImage = focused.image
            setStatus('Retrying with the detected object...')
            visionResult = await provider.identify(inferenceImage)
            setImagePreview(inferenceImage)
          } catch {
            // Preserve the original failure as the user-facing reason. The crop
            // is only allowed to rescue a scan, never replace it with a new error.
            throw originalError
          }
        }
      }
      if (recognitionId !== recognitionIdRef.current) return false

      setStatus('Checking disposal guidance...')
      const disposal = visionResult.kind === 'material'
        ? evaluateMaterialFallback(visionResult.materialCode)
        : getDisposalForItem(visionResult.itemCode)
      setPredictedItemCode(visionResult.kind === 'item' ? visionResult.itemCode : undefined)

      setResult(disposal)
      setResultCollapsed(false)
      saveScanHistory(disposal, method)
      setStage('idle')
      setStatus(undefined)
      void trackFeature(
        visionResult.kind === 'material' ? 'material_scan_success' : 'scan_success',
        'scan_success',
      )
      scheduleResultSurvey({
        inputMethod: method,
        predictedItemCode: visionResult.kind === 'item' ? visionResult.itemCode : undefined,
        destinationBinCode: disposal.destinationBin.code,
      })

      if (visionResult.kind === 'item' && provider.identifyComponents) {
        void provider.identifyComponents(inferenceImage, visionResult.itemCode).then((components) => {
          if (recognitionId === recognitionIdRef.current && components?.length) {
            setResult(getDisposalForItem(visionResult.itemCode, components))
          }
        })
      }
      return true
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error(error)
      }

      const appError = error instanceof AppError ? error : toAppError(error, 'INFERENCE_FAILED')
      setErrorCode(appError.code)
      setPredictedItemCode(undefined)
      setStage('idle')
      setStatus(undefined)
      void trackFeature(
        appError.code === 'MATERIAL_NOT_RECOGNISED' ? 'scan_feedback_requested' : 'scan_error',
        'scan_error',
      )
      pendingSurveyRef.current = {
        after: 'feedback-submit',
        context: { inputMethod: method },
      }
      return false
    }
  }, [])

  const resetRecognition = useCallback(() => {
    recognitionIdRef.current += 1
    if (surveyTimerRef.current !== undefined) {
      window.clearTimeout(surveyTimerRef.current)
      surveyTimerRef.current = undefined
    }
    setResult(undefined)
    setImagePreview(undefined)
    setErrorCode(undefined)
    setPredictedItemCode(undefined)
    setStatus(undefined)
    setStage('idle')
    setFeedbackDelivery(undefined)
    setSurveyOpen(false)
    setSurveyContext(undefined)
    setDetectorDebug(undefined)
    pendingSurveyRef.current = undefined
  }, [])

  const handleCameraCapture = useCallback(
    (dataUrl: string) => recogniseImage(dataUrl, 'camera', true),
    [recogniseImage],
  )

  const handleCameraError = useCallback((code: AppErrorCode) => {
    setErrorCode(code)
    setStage('idle')
  }, [])

  function handleFeedbackSubmitted(uploaded: boolean) {
    setFeedbackDelivery(uploaded ? 'uploaded' : 'queued')
    openPendingSurvey('feedback-submit')
  }

  function handleFeedbackCorrection(correctedCode: string, uploaded: boolean) {
    setFeedbackDelivery(uploaded ? 'uploaded' : 'queued')
    const context: SurveyContext = {
      inputMethod,
      predictedItemCode: correctedCode,
    }

    try {
      const correctedResult = getDisposalForItem(correctedCode)
      context.destinationBinCode = correctedResult.destinationBin.code
      setResult(correctedResult)
      setErrorCode(undefined)
      setResultCollapsed(false)
    } catch {
      // Unknown/not-listed feedback can be submitted without disposal guidance.
    }

    openPendingSurvey('feedback-submit', context)
  }

  const hasResult = Boolean(result)

  const layoutClassName = [
    'hero-layout recognition-layout',
    hasResult ? 'has-result' : '',
    hasResult && resultCollapsed ? 'result-collapsed' : '',
  ].filter(Boolean).join(' ')

  return (
    <section className={layoutClassName}>
      <div className="recognition-pane">
        {stage === 'camera' ? (
          <CameraCapture
            onCapture={handleCameraCapture}
            onCancel={resetRecognition}
            onError={handleCameraError}
          />
        ) : stage === 'processing' ? (
          <div className="hero-copy recognition-copy">
            <h1>
              <span className="headline-line">Scan your waste.</span>
              <span className="headline-line italic">Know where it goes</span>
            </h1>
            <StatusBlock message={status ?? 'Identifying item...'} />
          </div>
        ) : (
          <div className="hero-copy recognition-copy">
            <h1>
              <span className="headline-line">Scan your waste.</span>
              <span className="headline-line italic">Know where it goes</span>
            </h1>
            <p>
              One scan is all it takes. Instantly identify waste, sort it correctly, and explore better ways to recycle or reuse it.
            </p>
            <div className="button-row">
              <button type="button" className="primary-action" onClick={startCamera}>
                <ScanLine size={23} aria-hidden="true" />
                <span>Start Scanning</span>
              </button>
              <button type="button" className="secondary-action" onClick={openUpload}>
                <ImageUp size={23} aria-hidden="true" />
                <span>Upload an Image</span>
              </button>
            </div>
            {errorCode ? (
              <p className="inline-error" aria-live="polite">
                {messageForError(errorCode)}
                <span className="vi-note">{messageForErrorVi(errorCode)}</span>
              </p>
            ) : null}
            {!result ? (
              <div ref={feedbackSectionRef} className="recognition-feedback">
                <TrainingFeedbackPanel
                  key={imagePreview}
                  imagePreview={imagePreview}
                  predictedItemCode={predictedItemCode}
                  errorCode={errorCode}
                  inputMethod={inputMethod}
                  submittedStatus={feedbackDelivery}
                  onSubmitted={handleFeedbackSubmitted}
                  onCorrected={handleFeedbackCorrection}
                />
              </div>
            ) : null}
          </div>
        )}
      </div>

      {detectorDebug && import.meta.env.VITE_OBJECT_DETECTOR_DEBUG === 'true' ? (
        <details className="detector-debug-panel" open>
          <summary>
            <span>YOLO focus check</span>
            <strong>
              {detectorDebug.detection
                ? `${Math.round(detectorDebug.detection.confidence * 100)}% box`
                : 'No reliable box'}
            </strong>
          </summary>
          <div className="detector-debug-image">
            <img src={detectorDebug.image} alt="YOLO detector input" />
            {detectorDebug.detection ? (
              <i
                aria-label="Selected object bounding box"
                style={{
                  left: `${detectorDebug.detection.x * 100}%`,
                  top: `${detectorDebug.detection.y * 100}%`,
                  width: `${detectorDebug.detection.width * 100}%`,
                  height: `${detectorDebug.detection.height * 100}%`,
                }}
              />
            ) : null}
          </div>
          <p>The full focus frame is classified first. This box is used only to rescue an otherwise uncertain scan.</p>
        </details>
      ) : null}

      {result ? (
        <BinPanel
          bin={result.destinationBin}
          result={result}
          resultPanel
          collapsed={resultCollapsed}
          onToggleCollapsed={() => setResultCollapsed((current) => !current)}
          onClose={closeResult}
          footer={
            <TrainingFeedbackPanel
              imagePreview={imagePreview}
              predictedItemCode={predictedItemCode}
              inputMethod={inputMethod}
              submittedStatus={feedbackDelivery}
              onSubmitted={handleFeedbackSubmitted}
              onCorrected={handleFeedbackCorrection}
            />
          }
        />
      ) : null}

      {uploadOpen ? (
        <UploadDialog
          dragging={isDragging}
          onDraggingChange={setIsDragging}
          onClose={() => {
            setUploadOpen(false)
            setIsDragging(false)
          }}
          onFile={async (file) => {
            try {
              const dataUrl = await fileToDataUrl(file)
              setUploadOpen(false)
              setIsDragging(false)
              await recogniseImage(dataUrl, 'upload')
            } catch (error) {
              setUploadOpen(false)
              setIsDragging(false)
              setErrorCode(toAppError(error, 'IMAGE_INVALID').code)
              setStage('idle')
            }
          }}
        />
      ) : null}

      {surveyOpen && surveyContext ? (
        <UserSurveyModal
          inputMethod={surveyContext.inputMethod}
          predictedItemCode={surveyContext.predictedItemCode}
          destinationBinCode={surveyContext.destinationBinCode}
          onClose={() => {
            setSurveyOpen(false)
            setSurveyContext(undefined)
          }}
        />
      ) : null}
    </section>
  )
}

function UploadDialog({
  dragging,
  onDraggingChange,
  onClose,
  onFile,
}: {
  dragging: boolean
  onDraggingChange: (dragging: boolean) => void
  onClose: () => void
  onFile: (file: File) => void
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)

  function readFileList(files: FileList | null) {
    const file = files?.[0]
    if (file) {
      onFile(file)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="upload-dialog" role="dialog" aria-modal="true" aria-labelledby="upload-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="upload-dialog-header">
          <h2 id="upload-title">Images</h2>
        </header>
        <button type="button" className="modal-close" aria-label="Close upload dialog" onClick={onClose}>
          <X size={18} aria-hidden="true" />
        </button>
        <button
          type="button"
          className={dragging ? 'drop-zone dragging' : 'drop-zone'}
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => {
            event.preventDefault()
            onDraggingChange(true)
          }}
          onDragLeave={() => onDraggingChange(false)}
          onDrop={(event) => {
            event.preventDefault()
            onDraggingChange(false)
            readFileList(event.dataTransfer.files)
          }}
        >
          <span className="upload-cta">
            <ImageUp size={22} aria-hidden="true" />
            <span>Upload</span>
          </span>
          <span>Choose an image or drag and drop it here.<span className="vi-note">Chọn một ảnh hoặc kéo và thả ảnh vào đây.</span></span>
          <small>JPG, JPEG, PNG and WEBP. Max {maxImageMegabytes} MB.</small>
        </button>
        <input
          ref={inputRef}
          className="hidden-input"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => readFileList(event.target.files)}
        />
      </section>
    </div>
  )
}

function getDisposalForItem(itemCode: string, detectedComponents?: DetectedComponent[]) {
  const condition = getDefaultConditionForItem(itemCode)

  return evaluateDisposal({
    siteCode: 'default_station',
    itemCode,
    conditionAnswers: {
      default: condition,
      container_state: condition,
      plastic_cup_condition: condition,
      container_condition: condition,
      plastic_cleanliness: condition,
      paper_condition: condition,
    },
    locale: 'en',
    detectedComponents,
  })
}
