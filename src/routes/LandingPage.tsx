import { Check, Crop, ImageUp, RotateCcw, ScanLine, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BinPanel } from '../components/BinPanel'
import { StatusBlock } from '../components/StatusBlock'
import { TrainingFeedbackPanel } from '../components/TrainingFeedbackPanel'
import { CameraCapture } from '../features/camera/CameraCapture'
import { CropEditor } from '../features/camera/CropEditor'
import { fileToDataUrl } from '../features/camera/fileInput'
import { evaluateDisposal, getDefaultConditionForItem } from '../features/sorting/ruleEngine'
import { AppError, messageForError, toAppError } from '../lib/errors'
import { createVisionProvider } from '../providers/vision'
import { saveScanHistory } from '../services/history'
import type { AppErrorCode } from '../lib/errors'
import type { InputMethod, RuleEngineResult } from '../types/domain'

type RecognitionStage = 'idle' | 'camera' | 'preview' | 'processing'

const demoItems = [
  { itemCode: 'plastic_water_bottle', label: 'Bottle & Can', color: '#cb795f' },
  { itemCode: 'fruit_peel', label: 'Organic', color: '#3e8860' },
  { itemCode: 'plastic_takeaway_cup', label: 'Clean Plastic', color: '#b43b44' },
  { itemCode: 'cardboard_box', label: 'Paper', color: '#235398' },
  { itemCode: 'paper_cup', label: 'Landfill', color: '#793c36' },
  { itemCode: 'battery', label: 'Hazardous', color: '#f4ca59' },
]

export function LandingPage() {
  const [searchParams] = useSearchParams()
  const [stage, setStage] = useState<RecognitionStage>('idle')
  const [imagePreview, setImagePreview] = useState<string>()
  const [cropSource, setCropSource] = useState<string>()
  const [cropEditorOpen, setCropEditorOpen] = useState(false)
  const [inputMethod, setInputMethod] = useState<InputMethod>('camera')
  const [result, setResult] = useState<RuleEngineResult>()
  const [predictedItemCode, setPredictedItemCode] = useState<string>()
  const [status, setStatus] = useState<string>()
  const [errorCode, setErrorCode] = useState<AppErrorCode>()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [resultCollapsed, setResultCollapsed] = useState(false)
  const searchedItemCode = searchParams.get('item')
  const searchedSource = searchParams.get('source')

  useEffect(() => {
    if (!searchedItemCode) return

    try {
      const disposal = getDisposalForItem(searchedItemCode)
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
  }, [searchedItemCode, searchedSource])

  function startCamera() {
    setErrorCode(undefined)
    setInputMethod('camera')
    setStage('camera')
  }

  function openUpload() {
    setErrorCode(undefined)
    setUploadOpen(true)
  }

  function showImagePreview(dataUrl: string, method: InputMethod) {
    setImagePreview(dataUrl)
    setCropSource(dataUrl)
    setCropEditorOpen(true)
    setInputMethod(method)
    setStage('preview')
  }

  function openCropEditor() {
    if (!imagePreview) return
    setCropSource(imagePreview)
    setCropEditorOpen(true)
  }

  function applyCrop(dataUrl: string) {
    setImagePreview(dataUrl)
    setCropSource(undefined)
    setCropEditorOpen(false)
  }

  function cancelCrop() {
    setImagePreview(cropSource ?? imagePreview)
    setCropSource(undefined)
    setCropEditorOpen(false)
  }

  async function processImage() {
    if (!imagePreview) return

    setErrorCode(undefined)
    setStage('processing')

    try {
      setStatus('Preparing image...')
      await wait(160)
      setStatus('Identifying item...')
      const provider = await createVisionProvider()
      const visionResult = await provider.identify(imagePreview)
      setPredictedItemCode(visionResult.itemCode)

      setStatus('Checking disposal guidance...')
      await wait(160)

      const disposal = getDisposalForItem(visionResult.itemCode)

      setResult(disposal)
      setResultCollapsed(false)
      saveScanHistory(disposal, inputMethod)
      setStage('idle')
      setStatus(undefined)
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error(error)
      }

      const appError = error instanceof AppError ? error : toAppError(error, 'INFERENCE_FAILED')
      setErrorCode(appError.code)
      setPredictedItemCode(undefined)
      setStage('idle')
      setStatus(undefined)
    }
  }

  function retake() {
    setImagePreview(undefined)
    setCropSource(undefined)
    setCropEditorOpen(false)
    setErrorCode(undefined)
    setPredictedItemCode(undefined)
    setStage(inputMethod === 'camera' ? 'camera' : 'idle')
    if (inputMethod === 'upload') {
      setUploadOpen(true)
    }
  }

  function resetRecognition() {
    setImagePreview(undefined)
    setCropSource(undefined)
    setCropEditorOpen(false)
    setErrorCode(undefined)
    setPredictedItemCode(undefined)
    setStatus(undefined)
    setStage('idle')
  }

  function showDemoResult(itemCode: string) {
    try {
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

  return (
    <section className={hasResult ? 'hero-layout recognition-layout has-result' : 'hero-layout recognition-layout'}>
      <div className="recognition-pane">
        {stage === 'camera' ? (
          <CameraCapture
            onCapture={(dataUrl) => showImagePreview(dataUrl, 'camera')}
            onCancel={resetRecognition}
            onError={(code) => {
              setErrorCode(code)
              setStage('idle')
            }}
          />
        ) : stage === 'preview' && imagePreview ? (
          cropEditorOpen && cropSource ? (
            <CropEditor source={cropSource} onApply={applyCrop} onCancel={cancelCrop} onRetake={retake} />
          ) : (
            <div className="inline-preview">
              <div className="preview-frame">
                <img src={imagePreview} alt="Captured waste item preview" />
              </div>
              <div className="button-row full">
                <button type="button" className="primary-action" onClick={processImage}>
                  <Check size={17} aria-hidden="true" />
                  Use photo
                </button>
                <button type="button" className="secondary-action" onClick={openCropEditor}>
                  <Crop size={17} aria-hidden="true" />
                  Adjust crop
                </button>
                <button type="button" className="secondary-action" onClick={retake}>
                  <RotateCcw size={17} aria-hidden="true" />
                  Retake
                </button>
                <button type="button" className="ghost-action" onClick={resetRecognition}>
                  <X size={17} aria-hidden="true" />
                  Cancel
                </button>
              </div>
            </div>
          )
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
                    style={{ '--demo-color': item.color } as CSSProperties}
                    onClick={() => showDemoResult(item.itemCode)}
                  >
                    <i aria-hidden="true" />
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            {errorCode ? <p className="inline-error" aria-live="polite">{messageForError(errorCode)}</p> : null}
            <TrainingFeedbackPanel
              imagePreview={imagePreview}
              predictedItemCode={predictedItemCode}
              errorCode={errorCode}
              inputMethod={inputMethod}
              onCorrected={(correctedCode) => {
                try {
                  setResult(getDisposalForItem(correctedCode))
                  setErrorCode(undefined)
                  setResultCollapsed(false)
                } catch {
                  // The feedback panel only offers active reference-data classes.
                }
              }}
            />
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
              showImagePreview(dataUrl, 'upload')
            } catch (error) {
              setUploadOpen(false)
              setIsDragging(false)
              setErrorCode(toAppError(error, 'IMAGE_INVALID').code)
              setStage('idle')
            }
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

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function getDisposalForItem(itemCode: string) {
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
  })
}
