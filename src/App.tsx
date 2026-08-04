import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { FlowProvider } from './app/FlowContext'
import { AppShell } from './components/AppShell'
import { AboutPage } from './routes/AboutPage'
import { ConditionPage } from './routes/ConditionPage'
import { ConfirmPage } from './routes/ConfirmPage'
import { ErrorPage } from './routes/ErrorPage'
import { HistoryPage } from './routes/HistoryPage'
import { LandingPage } from './routes/LandingPage'
import { PreviewPage } from './routes/PreviewPage'
import { ResultPage } from './routes/ResultPage'
import { ReusePage } from './routes/ReusePage'
import { ScanPage } from './routes/ScanPage'
import { SearchPage } from './routes/SearchPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: 'scan', element: <ScanPage /> },
      { path: 'scan/preview', element: <PreviewPage /> },
      { path: 'scan/error', element: <ErrorPage /> },
      { path: 'confirm', element: <ConfirmPage /> },
      { path: 'condition', element: <ConditionPage /> },
      { path: 'result', element: <ResultPage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'history', element: <HistoryPage /> },
      { path: 'reuse/:id', element: <ReusePage /> },
      { path: 'about', element: <AboutPage /> },
    ],
  },
])

export default function App() {
  return (
    <FlowProvider>
      <RouterProvider router={router} />
    </FlowProvider>
  )
}
