import { useMemo, useState } from 'react'
import { formatDate, formatScore, scoreTone } from '../lib/format'
import {
  APPLICATION_STATUSES,
  STATUS_LABELS,
  type Application,
  type ApplicationStatus,
  type Job,
} from '../lib/types'
import { IconExternal, IconRefresh } from '../components/Icons'
import { Alert, EmptyState, Pill, Skeleton } from '../components/primitives'
import { DownloadButtons } from '../components/DownloadButtons'

type Props = {
  applications: Application[]
  jobs: Job[]
  loading: boolean
  error: string
  onRefresh: () => void
  onStatusChange: (id: number, status: ApplicationStatus) => Promise<unknown>
  onDelete: (id: number) => Promise<unknown>
}

/**
 * The application tracker.
 *
 * Previously a preview that faked pipeline stages from match scores. Every card
 * here is now a real `Application` row, and the column counts come from the
 * server's own aggregates, so the board cannot disagree with the list.
 */
export function ApplicationsPage({
  applications,
  jobs,
  loading,
  error,
  onRefresh,
  onStatusChange,
  onDelete,
}: Props) {
  const [filter, setFilter] = useState<ApplicationStatus | 'ALL'>('ALL')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [actionError, setActionError] = useState('')

  const jobById = useMemo(
    () => new Map(jobs.map((job) => [job.id, job])),
    [jobs],
  )

  const counts = useMemo(() => {
    const tally = Object.fromEntries(
      APPLICATION_STATUSES.map((status) => [status, 0]),
    ) as Record<ApplicationStatus, number>

    for (const application of applications) {
      tally[application.status] = (tally[application.status] ?? 0) + 1
    }
    return tally
  }, [applications])

  const visible = useMemo(
    () =>
      filter === 'ALL'
        ? applications
        : applications.filter((item) => item.status === filter),
    [applications, filter],
  )

  // Guarded so a failure cannot leave one card's controls stuck disabled.
  const changeStatus = async (id: number, status: ApplicationStatus) => {
    setBusyId(id)
    setActionError('')
    try {
      await onStatusChange(id, status)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not change the status.')
    } finally {
      setBusyId(null)
    }
  }

  const remove = async (id: number) => {
    setBusyId(id)
    setActionError('')
    try {
      await onDelete(id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not remove it.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="page stack">
      <section className="grid-stats">
        {APPLICATION_STATUSES.filter((status) => status !== 'WITHDRAWN').map((status) => (
          <button
            key={status}
            type="button"
            className={`stat stat-button${filter === status ? ' stat-active' : ''}`}
            onClick={() => setFilter(filter === status ? 'ALL' : status)}
            aria-pressed={filter === status}
          >
            <div className="stat-top">
              <span className="stat-label">{STATUS_LABELS[status]}</span>
            </div>
            <div className="stat-value">{loading ? '—' : counts[status]}</div>
          </button>
        ))}
      </section>

      {error ? (
        <Alert variant="danger" onDismiss={onRefresh}>
          {error}
        </Alert>
      ) : null}
      {actionError ? <Alert variant="danger">{actionError}</Alert> : null}

      <section className="card">
        <div className="card-head">
          <h3>Applications</h3>
          <div className="card-head-actions">
            <span className="pill">{loading ? '—' : visible.length}</span>
            <button
              type="button"
              className="btn btn-ghost btn-icon"
              onClick={onRefresh}
              disabled={loading}
              aria-label="Refresh applications"
              title="Refresh"
            >
              {loading ? <span className="spinner" /> : <IconRefresh size={16} />}
            </button>
          </div>
        </div>

        {loading ? (
          <div className="job-list">
            {Array.from({ length: 3 }).map((_, index) => (
              <div className="sk-row" key={index}>
                <Skeleton width={40} height={40} radius={12} />
                <div style={{ flex: 1, display: 'grid', gap: 7 }}>
                  <Skeleton width="45%" />
                  <Skeleton width="25%" height={11} />
                </div>
              </div>
            ))}
          </div>
        ) : visible.length === 0 ? (
          <EmptyState
            title={filter === 'ALL' ? 'No applications yet' : `No ${STATUS_LABELS[filter as ApplicationStatus].toLowerCase()} applications`}
            description={
              filter === 'ALL'
                ? 'Open a job and choose “Save Job” to start tracking it.'
                : 'Choose another status above, or clear the filter.'
            }
          />
        ) : (
          <div className="job-list">
            {visible.map((application) => {
              const job = jobById.get(application.job_detail?.id ?? application.job)
              const busy = busyId === application.id

              return (
                <div className="job-row" key={application.id} style={{ cursor: 'default' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                    <span className="avatar avatar-lg">
                      {(application.job_detail?.company || '?').slice(0, 2).toUpperCase()}
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div className="job-row-title" title={application.job_detail?.title}>
                        {application.job_detail?.title || 'Untitled role'}
                      </div>
                      <div className="job-row-meta">
                        <span>{application.job_detail?.company || 'Unknown company'}</span>
                        <Pill tone={`ap-${application.status.toLowerCase()}` as never}>
                          {STATUS_LABELS[application.status]}
                        </Pill>
                        {application.job_detail?.match_score != null ? (
                          <span className={`match tone-${scoreTone(application.job_detail.match_score)}`}>
                            {formatScore(application.job_detail.match_score)}
                          </span>
                        ) : null}
                        <span>{formatDate(application.updated_at)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="job-row-score">
                    <select
                      className="ap-select ap-select-sm"
                      value={application.status}
                      disabled={busy}
                      aria-label={`Change status for ${application.job_detail?.title ?? 'application'}`}
                      onChange={(event) =>
                        void changeStatus(application.id, event.target.value as ApplicationStatus)
                      }
                    >
                      {APPLICATION_STATUSES.map((status) => (
                        <option key={status} value={status}>
                          {STATUS_LABELS[status]}
                        </option>
                      ))}
                    </select>

                    {job ? (
                      <a
                        className="btn btn-ghost btn-sm"
                        href={job.url}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        Open Job
                        <IconExternal size={13} />
                      </a>
                    ) : null}

                    {application.tailored_resume ? (
                      <DownloadButtons resumeId={application.tailored_resume} label="" size="sm" />
                    ) : null}

                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => void remove(application.id)}
                      disabled={busy}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}

export default ApplicationsPage
