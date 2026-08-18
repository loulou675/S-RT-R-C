import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { startTrainingFeedbackSync } from './services/trainingFeedback.ts'
import { startUserSurveySync } from './services/userSurvey.ts'

startTrainingFeedbackSync()
startUserSurveySync()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
