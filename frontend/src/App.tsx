import { useCallback, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, api } from './lib/api'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/useAuth'
import {
  RequireAnonymous,
  RequireAuth,
  RequireMasterResume,
  RequireOnboardingSkills,
} from './auth/guards'
import { useApplications, useJobs, useResumes } from './hooks/useData'
import { useToasts } from './hooks/useToasts'
import type { Job, ViewKey } from './lib/types'
import { Sidebar } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import { Toasts } from './components/Toasts'
import { IconPlus, IconRefresh } from './components/Icons'
import { DashboardPage } from './pages/DashboardPage'
import { AnalyzePage } from './pages/AnalyzePage'
import { JobsPage } from './pages/JobsPage'
import { ApplicationsPage } from './pages/ApplicationsPage'
import { ResumesPage } from './pages/ResumesPage'
import { SettingsPage } from './pages/SettingsPage'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { SignupPage } from './pages/SignupPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { OnboardingSkillsPage } from './pages/OnboardingSkillsPage'
import { OnboardingYouPage } from './pages/OnboardingYouPage'
import { OnboardingAiPage } from './pages/OnboardingAiPage'

const HEADINGS: Record<ViewKey, { title: string; search: string }> = {
  dashboard: { title: 'Dashboard', search: 'Search jobs, companies…' },
  analyze: { title: 'Analyze a New Job', search: 'Search jobs, companies…' },
  jobs: { title: 'Jobs', search: 'Search jobs…' },
  resumes: { title: 'Resumes', search: 'Search resumes…' },
  applications: { title: 'Applications', search: 'Search applications…' },
  settings: { title: 'Settings', search: '' },
}

const PATHS: Record<ViewKey, string> = {
  dashboard: '/app/dashboard',
  analyze: '/app/analyze',
  jobs: '/app/jobs',
  resumes: '/app/resumes',
  applications: '/app/applications',
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
  const { logout, markSessionExpired, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState('')
  const [analyzeResult, setAnalyzeResult] = useState<Job | null>(null)
  const [shellSearch, setShellSearch] = useState('')

  const { jobs, loading, error, refresh } = useJobs()
  const {
    resumes,
    master,
    loading: resumesLoading,
    error: resumesError,
    refresh: refreshResumes,
  } = useResumes()
  const {
    applications,
    stats,
    loading: applicationsLoading,
    error: applicationsError,
    refresh: refreshApplications,
    create: createApplication,
    setStatus: setApplicationStatus,
    remove: removeApplication,
  } = useApplications()
  const { toasts, dismiss, notify } = useToasts()

  const applicationForJob = useCallback(
    (jobId: number) => applications.find((item) => item.job === jobId) ?? null,
    [applications],
  )

  const view = (PATH_TO_VIEW[location.pathname] ?? 'dashboard') as ViewKey
  const heading = HEADINGS[view] ?? HEADINGS.dashboard

  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(' ')

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

      <Sidebar
        view={view}
        onNavigate={handleNavigate}
        jobCount={jobs.length}
        email={user?.email ?? ''}
        displayName={displayName}
        onLogout={() => { void logout() }}
      />

      <div className="main-panel">
        <Topbar
          title={heading.title}
          search={heading.search || undefined}
          searchValue={shellSearch}
          onSearchChange={setShellSearch}
          avatarLabel={displayName || user?.email}
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
              {view === 'jobs' ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => handleNavigate('analyze')}
                >
                  <IconPlus size={15} />
                  Analyze New Job
                </button>
              ) : null}
            </>
          }
        />

        {view === 'dashboard' ? (
          <DashboardPage
            applicationForJob={applicationForJob}
            onCreateApplication={(jobId: number) => createApplication(jobId)}
            onApplicationStatus={setApplicationStatus}
            onDeleteApplication={removeApplication}
            applications={applications}
            stats={stats}
            applicationsLoading={applicationsLoading}
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

        {view === 'applications' ? (
          <ApplicationsPage
            applications={applications}
            jobs={jobs}
            loading={applicationsLoading}
            error={applicationsError}
            onRefresh={() => void refreshApplications()}
            onStatusChange={setApplicationStatus}
            onDelete={removeApplication}
          />
        ) : null}

        {view === 'resumes' ? (
          <ResumesPage
            resumes={resumes}
            master={master}
            jobs={jobs}
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

        {/* Onboarding — signed in, completing setup in order */}
        <Route element={<RequireAuth />}>
          <Route path="/setup/resume" element={<OnboardingPage />} />
          <Route
            path="/setup/skills"
            element={<RequireOnboardingSkills><OnboardingSkillsPage /></RequireOnboardingSkills>}
          />
          <Route path="/setup/you" element={<OnboardingYouPage />} />
          <Route path="/setup/ai" element={<OnboardingAiPage />} />
        </Route>

        {/* Private workspace — requires a master resume to be useful */}
        <Route element={<RequireAuth />}>
          <Route path="/app" element={<RequireMasterResume />}>
            <Route path="dashboard" element={<AppShell />} />
            <Route path="analyze" element={<AppShell />} />
            <Route path="jobs" element={<AppShell />} />
            <Route path="resumes" element={<AppShell />} />
            <Route path="applications" element={<AppShell />} />
            <Route path="settings" element={<AppShell />} />
            <Route index element={<Navigate to="/app/dashboard" replace />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}

