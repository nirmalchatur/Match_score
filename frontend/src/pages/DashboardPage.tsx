import { useCallback, useMemo, useState } from 'react'
import { formatScore, scoreTone } from '../lib/format'
import type { Application, ApplicationStatus, DashboardStats, Job, Resume } from '../lib/types'
import {
  IconBriefcase,
  IconRefresh,
  IconTarget,
  IconTrend,
  IconZap,
} from '../components/Icons'
import { JobRow } from '../components/JobRow'
import { ApplicationTracker } from '../components/ApplicationTracker'
import { JobDetail } from '../components/JobDetail'
import { STATUS_LABELS } from '../lib/types'
import { UrlForm } from '../components/UrlForm'
import { Alert, EmptyState, JobRowSkeleton, Pill, Skeleton, StatCard } from '../components/primitives'

type Props = {
  jobs: Job[]
  loading: boolean
  error: string
  refreshing: boolean
  masterResume: Resume | null
  analyzing: boolean
  onRefresh: () => void
  onAnalyze: (url: string) => void
  /** Real aggregates from the server. Never derived from a hardcoded value. */
  stats: DashboardStats | null
  applications: Application[]
  applicationsLoading: boolean
  applicationForJob: (jobId: number) => Application | null
  onCreateApplication: (jobId: number) => Promise<unknown>
  onApplicationStatus: (id: number, status: ApplicationStatus) => Promise<unknown>
  onDeleteApplication: (id: number) => Promise<unknown>
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
  stats,
  applications,
  applicationsLoading,
  applicationForJob,
  onCreateApplication,
  onApplicationStatus,
  onDeleteApplication,
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
  const average = stats?.match.average ?? null
  const recent = jobs.slice(0, 8)

  // Counters come from the API's own aggregates so the dashboard and the
  // tracker can never disagree. `?? 0` is the honest empty state, not a
  // placeholder for missing data.
  const applicationCount = stats?.applications.total ?? 0
  const interviewCount = stats?.applications.interviews ?? 0
  const offerCount = stats?.applications.offers ?? 0

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
          label="Applications"
          value={applicationsLoading ? '—' : applicationCount}
          icon={<IconTarget size={16} />}
          tone="amber"
          hint={
            applicationCount
              ? `${interviewCount} interview · ${offerCount} offer`
              : 'No applications tracked yet'
          }
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

      <section className="card">
        <div className="card-head">
          <h3>Recent applications</h3>
          <div className="card-head-actions">
            <span className="pill">{applicationsLoading ? '—' : applications.length}</span>
          </div>
        </div>

        {applicationsLoading ? (
          <div className="job-list">
            {Array.from({ length: 2 }).map((_, index) => (
              <div className="sk-row" key={index}>
                <Skeleton width="40%" />
                <Skeleton width="20%" height={11} />
              </div>
            ))}
          </div>
        ) : applications.length === 0 ? (
          <EmptyState
            title="No applications yet"
            description="Open a job and choose “Save Job” to start tracking your pipeline."
          />
        ) : (
          <div className="job-list">
            {applications.slice(0, 5).map((application) => (
              <div
                className="job-row"
                key={application.id}
                style={{ cursor: 'default' }}
              >
                <div style={{ minWidth: 0 }}>
                  <div className="job-row-title">{application.job_detail?.title}</div>
                  <div className="job-row-meta">
                    <span>{application.job_detail?.company}</span>
                    {application.job_detail?.match_score != null ? (
                      <span className={`match tone-${scoreTone(application.job_detail.match_score)}`}>
                        {formatScore(application.job_detail.match_score)}
                      </span>
                    ) : null}
                  </div>
                </div>
                <Pill tone={`ap-${application.status.toLowerCase()}` as never}>
                  {STATUS_LABELS[application.status]}
                </Pill>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* The tracker owns its own data: it reads and PATCHes applications
          directly, so it does not need (or wait on) the dashboard payload. */}
      <ApplicationTracker />

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
            <JobDetail
              job={selectedJob}
              application={applicationForJob(selectedJob.id)}
              onCreateApplication={() => onCreateApplication(selectedJob.id)}
              onApplicationStatus={onApplicationStatus}
              onDeleteApplication={onDeleteApplication}
            />
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
