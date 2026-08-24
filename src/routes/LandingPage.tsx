import { ImageUp, ScanLine, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BinPanel } from '../components/BinPanel'
import { StatusBlock } from '../components/StatusBlock'
import { TrainingFeedbackPanel } from '../components/TrainingFeedbackPanel'
import { UserSurveyModal } from '../components/UserSurveyModal'
import { CameraCapture } from '../features/camera/CameraCapture'
import { fileToDataUrl } from '../features/camera/fileInput'
import { evaluateDisposal, evaluateMaterialFallback, getDefaultConditionForItem } from '../features/sorting/ruleEngine'
import { AppError, messageForError, toAppError } from '../lib/errors'
import { createVisionProvider } from '../providers/vision'
import { saveScanHistory } from '../services/history'
import { trackFeature } from '../services/siteAnalytics'
import type { AppErrorCode } from '../lib/errors'
import type { BroadMaterialCode, DetectedComponent, InputMethod, RuleEngineResult } from '../types/domain'

type RecognitionStage = 'idle' | 'camera' | 'processing'

const demoItems = [
  { itemCode: 'plastic_water_bottle', label: 'Bottle & Can', color: '#f08c21', ink: '#171411' },
  { itemCode: 'fruit_peel', label: 'Organic', color: '#b4b534', ink: '#171411' },
  { itemCode: 'plastic_takeaway_cup', label: 'Clean Plastic', color: '#bd5961', ink: '#fffaf4' },
  { itemCode: 'cardboard_box', label: 'Paper', color: '#6698cc', ink: '#171411' },
  { itemCode: 'paper_cup', label: 'Landfill', color: '#673c33', ink: '#fffaf4' },
  { itemCode: 'battery', label: 'Hazardous', color: '#f4d68c', ink: '#171411' },
]

// Bump this when the survey UI changes so an existing browser session can see the new version once.
const surveySessionKey = 'sot-rac-post-scan-survey-v2-shown'
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
  const recognitionIdRef = useRef(0)
  const feedbackSectionRef = useRef<HTMLDivElement | null>(null)
  const searchedItemCode = searchParams.get('item')
  const searchedMaterialCode = searchParams.get('material') as BroadMaterialCode | null
  const searchedSource = searchParams.get('source')

  useEffect(() => {
    const prepareModel = () => {
      void createVisionProvider().then((provider) => provider.prepare?.()).catch(() => undefined)
    }
    const idleId = window.setTimeout(prepareModel, 150)
    return () => window.clearTimeout(idleId)
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
    if (stage !== 'idle' || !errorCode || !imagePreview) return

    const frame = window.requestAnimationFrame(() => {
      feedbackSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [errorCode, imagePreview, stage])

  function closeResult() {
    recognitionIdRef.current += 1
    setResult(undefined)
    setResultCollapsed(false)
    setErrorCode(undefined)
    setSurveyOpen(false)
  }

  function startCamera() {
    void trackFeature('camera_scan')
    closeResult()
    setFeedbackDelivery(undefined)
    setImagePreview(undefined)
    setPredictedItemCode(undefined)
    setInputMethod('camera')
    setStage('camera')
  }

  function openUpload() {
    void trackFeature('image_upload')
    closeResult()
    setFeedbackDelivery(undefined)
    setImagePreview(undefined)
    setPredictedItemCode(undefined)
    setUploadOpen(true)
  }

  const recogniseImage = useCallback(async (dataUrl: string, method: InputMethod, keepCameraOpen = false) => {
    const recognitionId = recognitionIdRef.current + 1
    recognitionIdRef.current = recognitionId
    setFeedbackDelivery(undefined)
    setImagePreview(dataUrl)
    setInputMethod(method)
    setErrorCode(undefined)
    if (!keepCameraOpen) setStage('processing')

    try {
      setStatus('Preparing image...')
      setStatus('Identifying item...')
      const provider = await createVisionProvider()
      const visionResult = await provider.identify(dataUrl)
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

      window.setTimeout(() => {
        if (recognitionId === recognitionIdRef.current && markSurveyShownForSession()) {
          setSurveyOpen(true)
        }
      }, 520)

      if (visionResult.kind === 'item' && provider.identifyComponents) {
        void provider.identifyComponents(dataUrl, visionResult.itemCode).then((components) => {
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
      return false
    }
  }, [])

  const resetRecognition = useCallback(() => {
    recognitionIdRef.current += 1
    setResult(undefined)
    setImagePreview(undefined)
    setErrorCode(undefined)
    setPredictedItemCode(undefined)
    setStatus(undefined)
    setStage('idle')
    setFeedbackDelivery(undefined)
    setSurveyOpen(false)
  }, [])

  const handleCameraCapture = useCallback(
    (dataUrl: string) => recogniseImage(dataUrl, 'camera', true),
    [recogniseImage],
  )

  const handleCameraError = useCallback((code: AppErrorCode) => {
    setErrorCode(code)
    setStage('idle')
  }, [])

  function showDemoResult(itemCode: string) {
    void trackFeature('demo_result')
    try {
      setFeedbackDelivery(undefined)
      const disposal = getDisposalForItem(itemCode)
      setResult(disposal)
      setResultCollapsed(false)
      setErrorCode(undefined)
      setStage('idle')
      setStatus(undefined)
    } catch (error) {
      const appError = error instanceof AppError ? error : toAppError(error, 'RULE_NOT_FOUND')
      setErrorCode(appError.code)
    }
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
                <ScanLine size={17} aria-hidden="true" />
                Start Scanning
              </button>
              <button type="button" className="secondary-action" onClick={openUpload}>
                <ImageUp size={17} aria-hidden="true" />
                Upload an Image
              </button>
            </div>
            <div className="demo-palette" aria-label="Demo bin colors">
              <span>Demo bin tones</span>
              <div>
                {demoItems.map((item) => (
                  <button
                    type="button"
                    key={item.itemCode}
                    style={{ '--demo-color': item.color, '--demo-ink': item.ink } as CSSProperties}
                    onClick={() => showDemoResult(item.itemCode)}
                  >
                    <i aria-hidden="true" />
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            {errorCode ? <p className="inline-error" aria-live="polite">{messageForError(errorCode)}</p> : null}
            {!result ? (
              <div ref={feedbackSectionRef} className="recognition-feedback">
                <TrainingFeedbackPanel
                  key={imagePreview}
                  imagePreview={imagePreview}
                  predictedItemCode={predictedItemCode}
                  errorCode={errorCode}
                  inputMethod={inputMethod}
                  submittedStatus={feedbackDelivery}
                  onSubmitted={(uploaded) => setFeedbackDelivery(uploaded ? 'uploaded' : 'queued')}
                  onCorrected={(correctedCode, uploaded) => {
                    try {
                      setFeedbackDelivery(uploaded ? 'uploaded' : 'queued')
                      setResult(getDisposalForItem(correctedCode))
                      setErrorCode(undefined)
                      setResultCollapsed(false)
                    } catch {
                      // The feedback panel only offers active reference-data classes.
                    }
                  }}
                />
              </div>
            ) : null}
          </div>
        )}
      </div>

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
              onSubmitted={(uploaded) => setFeedbackDelivery(uploaded ? 'uploaded' : 'queued')}
              onCorrected={(correctedCode, uploaded) => {
                try {
                  setFeedbackDelivery(uploaded ? 'uploaded' : 'queued')
                  setResult(getDisposalForItem(correctedCode))
                  setErrorCode(undefined)
                  setResultCollapsed(false)
                } catch {
                  // The feedback panel only offers active reference-data classes.
                }
              }}
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

      {surveyOpen && result ? (
        <UserSurveyModal
          inputMethod={inputMethod}
          predictedItemCode={predictedItemCode}
          destinationBinCode={result.destinationBin.code}
          onClose={() => setSurveyOpen(false)}
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
            Upload
          </span>
          <span>Choose images or drag & drop it here.</span>
          <small>JPG, JPEG, PNG and WEBP. Max 20 MB.</small>
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
