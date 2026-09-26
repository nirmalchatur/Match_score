import { useMemo } from 'react'
import { formatDate, formatScore, initials, scoreTone } from '../lib/format'
import type { Job } from '../lib/types'
import { IconPlus } from '../components/Icons'
import { Alert, EmptyState, Pill } from '../components/primitives'
import { UrlForm } from '../components/UrlForm'

/**
 * The six columns of the reference board.
 *
 * Application tracking is a planned feature, so the columns are derived from
 * the analysed jobs rather than a persisted status the backend does not have
 * yet. Each analysed job is placed in the column its match score maps to.
 */
const COLUMNS = [
  { key: 'saved', label: 'Saved', test: (score: number | null) => score == null || score < 50 },
  { key: 'applied', label: 'Applied', test: (score: number | null) => score != null && score >= 50 && score < 60 },
  { key: 'assessment', label: 'Assessment', test: (score: number | null) => score != null && score >= 60 && score < 70 },
  { key: 'interview', label: 'Interview', test: (score: number | null) => score != null && score >= 70 && score < 80 },
  { key: 'offer', label: 'Offer', test: (score: number | null) => score != null && score >= 80 && score < 90 },
  { key: 'rejected', label: 'Rejected', test: (score: number | null) => score != null && score >= 90 },
]

type ColumnKey = (typeof COLUMNS)[number]['key']

type Props = {
  jobs: Job[]
  analyzing: boolean
  onAnalyze: (url: string) => void
}

export function ApplicationsPage({ jobs, analyzing, onAnalyze }: Props) {
  const grouped = useMemo(() => {
    const map = Object.fromEntries(COLUMNS.map((c) => [c.key, [] as Job[]])) as Record<
      ColumnKey,
      Job[]
    >

    for (const job of jobs) {
      const column = COLUMNS.find((c) => c.test(job.match_score))
      if (column) map[column.key].push(job)
    }

    return map
  }, [jobs])

  return (
    <div className="page stack">
      <Alert variant="warning">
        <strong>Application Tracker is coming soon.</strong> This board previews the upcoming
        feature by mapping your analyzed jobs onto pipeline stages. Drag-and-drop and status
        management are planned for a future release.
      </Alert>

      {jobs.length === 0 ? (
        <section className="card">
          <div className="card-body">
            <div className="section-title">Analyze a new job</div>
            <p className="stat-hint" style={{ marginTop: 4, marginBottom: 16 }}>
              Paste a supported job posting URL to get started.
            </p>
            <UrlForm onSubmit={onAnalyze} busy={analyzing} />
          </div>
        </section>
      ) : null}

      {jobs.length === 0 ? (
        <div className="card">
          <EmptyState
            title="No applications yet"
            description="Analyzed jobs will be grouped into pipeline stages here."
          />
        </div>
      ) : (
        <>
          <div className="kanban">
            {COLUMNS.map((column) => {
              const items = grouped[column.key]

              return (
                <div className="kanban-col" data-tone={column.key} key={column.key}>
                  <div className="kanban-head">
                    {column.label}
                    <span className="kanban-count">{items.length}</span>
                  </div>

                  <div className="kanban-cards">
                    {items.map((job) => {
                      const tone = scoreTone(job.match_score)

                      return (
                        <div className="kanban-card" key={job.id}>
                          <div className="kanban-card-top">
                            <span className="avatar">{initials(job.company)}</span>
                            <span style={{ minWidth: 0 }}>
                              <span className="kanban-company">{job.company || 'Unknown'}</span>
                              <span className="kanban-role">{job.title || 'Untitled role'}</span>
                            </span>
                          </div>

                          <div className="kanban-foot">
                            <span className={`match tone-${tone}`} style={{ flex: 1 }}>
                              <span className="match-bar">
                                <span
                                  style={{
                                    width: `${Math.max(0, Math.min(100, job.match_score ?? 0))}%`,
                                  }}
                                />
                              </span>
                              <span className="match-value">{formatScore(job.match_score)}</span>
                            </span>
                            <span className="kanban-date">
                              {job.created_at ? formatDate(job.created_at) : '—'}
                            </span>
                          </div>
                        </div>
                      )
                    })}

                    <button className="kanban-add" type="button" disabled>
                      <IconPlus size={12} />
                      Add
                    </button>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="section-row">
            <span className="stat-hint">
              {jobs.length} analyzed job{jobs.length === 1 ? '' : 's'} mapped onto the board.
            </span>
            <div className="section-row-actions">
              <Pill tone="accent">Preview</Pill>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default ApplicationsPage
