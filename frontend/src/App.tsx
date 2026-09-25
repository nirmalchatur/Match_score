import { useCallback, useMemo, useState } from 'react'
import { ApiError, api } from './lib/api'
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

const HEADINGS: Record<ViewKey, { eyebrow: string; title: string }> = {
  dashboard: { eyebrow: 'Dashboard', title: 'Analyze a Job' },
  analyze: { eyebrow: 'Pipeline', title: 'New Analysis' },
  jobs: { eyebrow: 'Library', title: 'Jobs' },
  resumes: { eyebrow: 'Library', title: 'Resumes' },
}

export default function App() {
  const [view, setView] = useState<ViewKey>('dashboard')
  const [selectedId, setSelectedId] = useState<number | null>(null)
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

  // Derived: the explicitly picked job, else the newest one in the list.
  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedId) ?? jobs[0] ?? null,
    [jobs, selectedId],
  )

  const handleSelectJob = useCallback((job: Job) => {
    setSelectedId(job.id)
  }, [])

  const handleAnalyze = useCallback(
    async (url: string) => {
      setAnalyzing(true)
      setAnalyzeError('')
      try {
        const data = await api.analyzeJob(url)
        setAnalyzeResult(data.job)
        setSelectedId(data.job.id)
        notify.success(
          'Analysis complete',
          `${data.job.company || 'Job'} — ${data.job.title || 'untitled role'}`,
        )
        await refresh()
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : 'Something went wrong while analyzing the job.'
        setAnalyzeError(message)
        notify.error('Analysis failed', message)
      } finally {
        setAnalyzing(false)
      }
    },
    [notify, refresh],
  )

  const handleNavigate = useCallback((next: ViewKey) => {
    setView(next)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  const heading = HEADINGS[view]

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
            selectedJob={selectedJob}
            masterResume={master}
            analyzing={analyzing}
            onRefresh={() => void refresh()}
            onSelectJob={handleSelectJob}
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
      </div>

      <Toasts toasts={toasts} onDismiss={dismiss} />
    </div>
  )
}
