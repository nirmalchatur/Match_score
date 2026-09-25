import { useCallback, useMemo, useState } from 'react'
import { formatScore } from '../lib/format'
import type { Job, Resume } from '../lib/types'
import {
  IconBriefcase,
  IconRefresh,
  IconTarget,
  IconTrend,
  IconZap,
} from '../components/Icons'
import { JobRow } from '../components/JobRow'
import { JobDetail } from '../components/JobDetail'
import { UrlForm } from '../components/UrlForm'
import { Alert, EmptyState, JobRowSkeleton, StatCard } from '../components/primitives'

type Props = {
  jobs: Job[]
  loading: boolean
  error: string
  refreshing: boolean
  masterResume: Resume | null
  analyzing: boolean
  onRefresh: () => void
  onAnalyze: (url: string) => void
}

export function DashboardPage({
  jobs,
  loading,
  error,
  refreshing,
  masterResume,
  analyzing,
  onRefresh,
  onAnalyze,
}: Props) {
  // Selection is derived, not synced: the picked job, else the newest.
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedId) ?? jobs[0] ?? null,
    [jobs, selectedId],
  )

  const handleSelectJob = useCallback((job: Job) => {
    setSelectedId(job.id)
  }, [])

  const scored = jobs.filter((job) => job.match_score != null)
  const average = scored.length
    ? scored.reduce((sum, job) => sum + (job.match_score ?? 0), 0) / scored.length
    : null
  const strong = scored.filter((job) => (job.match_score ?? 0) >= 80).length
  const recent = jobs.slice(0, 8)

  return (
    <div className="page stack">
      <section className="grid-stats">
        <StatCard
          label="Jobs tracked"
          value={loading ? '—' : jobs.length}
          icon={<IconBriefcase size={16} />}
          tone="blue"
          hint={jobs.length > 0 ? 'Across all analyzed postings' : 'Nothing analyzed yet'}
        />
        <StatCard
          label="Average match"
          value={loading ? '—' : formatScore(average)}
          icon={<IconTrend size={16} />}
          tone="green"
          hint={scored.length > 0 ? `Based on ${scored.length} scored roles` : 'No scores yet'}
        />
        <StatCard
          label="Strong matches"
          value={loading ? '—' : strong}
          icon={<IconTarget size={16} />}
          tone="amber"
          hint="Scoring 80% or higher"
        />
        <StatCard
          label="Master resume"
          value={masterResume ? 'Ready' : 'Missing'}
          icon={<IconZap size={16} />}
          hint={masterResume ? masterResume.name : 'Upload one to enable scoring'}
        />
      </section>

      {error ? (
        <Alert variant="danger" onDismiss={onRefresh}>
          {error}
        </Alert>
      ) : null}

      <section className="card">
        <div className="card-body">
          <div className="section-title">Analyze a new job</div>
          <UrlForm onSubmit={onAnalyze} busy={analyzing} />
        </div>
      </section>

      <section className="grid-dashboard">
        <div className="card sticky-col">
          <div className="card-head">
            <h3>Recent jobs</h3>
            <div className="card-head-actions">
              <button
                type="button"
                className="btn btn-ghost btn-icon"
                onClick={onRefresh}
                disabled={refreshing}
                aria-label="Refresh jobs"
                title="Refresh"
              >
                {refreshing ? <span className="spinner" /> : <IconRefresh size={16} />}
              </button>
            </div>
          </div>

          {loading ? (
            <div className="job-list">
              {Array.from({ length: 4 }).map((_, index) => (
                <JobRowSkeleton key={index} />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <EmptyState
              title="No jobs yet"
              description="Paste a Greenhouse job URL above to run your first analysis."
            />
          ) : (
            <div className="job-list">
              {recent.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  selected={selectedJob?.id === job.id}
                  onSelect={handleSelectJob}
                />
              ))}
            </div>
          )}
        </div>

        <div>
          {selectedJob ? (
            <JobDetail job={selectedJob} />
          ) : (
            <div className="card">
              <EmptyState
                title="Nothing selected"
                description="Pick a job from the list to inspect its match score, pipeline, and full description."
              />
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
