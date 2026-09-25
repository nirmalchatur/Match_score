import { useCallback, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, api } from './lib/api'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/useAuth'
import { RequireAnonymous, RequireAuth, RequireMasterResume } from './auth/guards'
import { useJobs, useResumes } from './hooks/useData'
import { useToasts } from './hooks/useToasts'
import type { Job, ViewKey } from './lib/types'
import { Sidebar } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import { Toasts } from './components/Toasts'
import { IconRefresh } from './components/Icons'
import { DashboardPage } from './pages/DashboardPage'
import { AnalyzePage } from './pages/AnalyzePage'
import { JobsPage } from './pages/JobsPage'
import { ResumesPage } from './pages/ResumesPage'
import { SettingsPage } from './pages/SettingsPage'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { SignupPage } from './pages/SignupPage'
import { OnboardingPage } from './pages/OnboardingPage'

const HEADINGS: Record<ViewKey, { eyebrow: string; title: string }> = {
  dashboard: { eyebrow: 'Workspace', title: 'Dashboard' },
  analyze: { eyebrow: 'Pipeline', title: 'New Analysis' },
  jobs: { eyebrow: 'Library', title: 'Jobs' },
  resumes: { eyebrow: 'Library', title: 'Resumes' },
  settings: { eyebrow: 'Account', title: 'Settings' },
}

const PATHS: Record<ViewKey, string> = {
  dashboard: '/app/dashboard',
  analyze: '/app/analyze',
  jobs: '/app/jobs',
  resumes: '/app/resumes',
  settings: '/app/settings',
}

const PATH_TO_VIEW = Object.entries(PATHS).reduce<Record<string, ViewKey>>(
  (acc, [key, path]) => ({ ...acc, [path]: key as ViewKey }),
  {},
)

/**
 * The authenticated workspace. Owns the shared job/resume state and renders
 * the dashboard pages for whichever /app route is active.
 */
function AppShell() {
  const { markSessionExpired } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState('')
  const [analyzeResult, setAnalyzeResult] = useState<Job | null>(null)

  const { jobs, loading, error, online, refresh } = useJobs()
  const {
    resumes,
    master,
    loading: resumesLoading,
    error: resumesError,
    refresh: refreshResumes,
  } = useResumes()
  const { toasts, dismiss, notify } = useToasts()

  const view = (PATH_TO_VIEW[location.pathname] ?? 'dashboard') as ViewKey
  const heading = HEADINGS[view] ?? HEADINGS.dashboard

  const handleNavigate = useCallback(
    (key: ViewKey) => {
      navigate(PATHS[key] ?? '/app/dashboard')
    },
    [navigate],
  )

  const handleAnalyze = useCallback(
    async (url: string) => {
      setAnalyzing(true)
      setAnalyzeError('')
      try {
        const data = await api.analyzeJob(url)
        setAnalyzeResult(data.job)
        notify.success(
          'Analysis complete',
          `${data.job.company || 'Job'} — ${data.job.title || 'untitled role'}`,
        )
        await refresh()
      } catch (err) {
        // A 401/403 means the session lapsed: send the user to sign in rather
        // than showing a generic failure.
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          markSessionExpired()
          navigate('/login', { replace: true })
          return
        }
        const message =
          err instanceof ApiError ? err.message : 'Something went wrong while analyzing the job.'
        setAnalyzeError(message)
        notify.error('Analysis failed', message)
      } finally {
        setAnalyzing(false)
      }
    },
    [markSessionExpired, navigate, notify, refresh],
  )

  return (
    <div className="app-shell">
      <div className="bg-fx" aria-hidden="true" />

      <Sidebar view={view} onNavigate={handleNavigate} jobCount={jobs.length} online={online} />

      <div className="main-panel">
        <Topbar
          eyebrow={heading.eyebrow}
          title={heading.title}
          actions={
            <>
              <button
                type="button"
                className="btn btn-ghost btn-icon"
                onClick={() => void refresh()}
                disabled={loading}
                aria-label="Refresh data"
                title="Refresh"
              >
                {loading ? <span className="spinner" /> : <IconRefresh size={16} />}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => handleNavigate('analyze')}
              >
                New analysis
              </button>
            </>
          }
        />

        {view === 'dashboard' ? (
          <DashboardPage
            jobs={jobs}
            loading={loading}
            error={error}
            refreshing={loading}
            masterResume={master}
            analyzing={analyzing}
            onRefresh={() => void refresh()}
            onAnalyze={(url) => void handleAnalyze(url)}
          />
        ) : null}

        {view === 'analyze' ? (
          <AnalyzePage
            analyzing={analyzing}
            error={analyzeError}
            result={analyzeResult}
            onAnalyze={(url) => void handleAnalyze(url)}
          />
        ) : null}

        {view === 'jobs' ? <JobsPage /> : null}

        {view === 'resumes' ? (
          <ResumesPage
            resumes={resumes}
            master={master}
            loading={resumesLoading}
            error={resumesError}
            onRefresh={() => void refreshResumes()}
          />
        ) : null}

        {view === 'settings' ? <SettingsPage /> : null}
      </div>

      <Toasts toasts={toasts} onDismiss={dismiss} />
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public marketing + auth */}
        <Route element={<RequireAnonymous />}>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
        </Route>

        {/* Onboarding — signed in, but may not have a master resume yet */}
        <Route element={<RequireAuth />}>
          <Route path="/setup/resume" element={<OnboardingPage />} />
        </Route>

        {/* Private workspace — requires a master resume to be useful */}
        <Route element={<RequireAuth />}>
          <Route path="/app" element={<RequireMasterResume />}>
            <Route path="dashboard" element={<AppShell />} />
            <Route path="analyze" element={<AppShell />} />
            <Route path="jobs" element={<AppShell />} />
            <Route path="resumes" element={<AppShell />} />
            <Route path="settings" element={<AppShell />} />
            <Route index element={<Navigate to="/app/dashboard" replace />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}

