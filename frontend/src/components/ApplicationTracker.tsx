import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, api } from '../lib/api'
import { atsLabel } from '../lib/format'
import { Alert } from './primitives'
import { IconCheck, IconRefresh } from './Icons'
import {
  APPLICATION_STATUSES,
  type Application,
  type ApplicationStatus,
} from '../lib/types'

/**
 * The application tracker: one row per application, one control to move it.
 *
 * A real <table> rather than a grid of divs. This is the one screen in the
 * product that is genuinely tabular -- fixed columns, many rows, a value that
 * has to be compared down the column -- and a div grid cannot align columns
 * or sort without reimplementing what the browser already does.
 *
 * Why a <select> for the stage
 * ---------------------------
 * The user asked to write "OA given", "moved to third round". Those are a
 * small closed set, and the server already validates against it. Free text
 * would make every row a typo and quietly fail a PATCH that the UI looked
 * like it had saved. The "round" detail lives in the notes field, which is
 * free text for exactly this reason.
 */
const LABELS: Record<ApplicationStatus, string> = {
  SAVED: 'Saved',
  APPLIED: 'Applied',
  ASSESSMENT: 'Assessment / OA',
  INTERVIEW: 'Interview',
  OFFER: 'Offer',
  REJECTED: 'Rejected',
  WITHDRAWN: 'Withdrawn',
}

/** Stages that mean the employer is still deciding. Drives the row emphasis. */
const LIVE: ApplicationStatus[] = ['APPLIED', 'ASSESSMENT', 'INTERVIEW']

function toneFor(status: ApplicationStatus): string {
  if (status === 'OFFER') return 'st-offer'
  if (status === 'REJECTED' || status === 'WITHDRAWN') return 'st-closed'
  if (LIVE.includes(status)) return 'st-live'
  return 'st-idle'
}

export function ApplicationTracker() {
  const [rows, setRows] = useState<Application[] | null>(null)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<ApplicationStatus | ''>('')

  const load = useCallback(async () => {
    setError('')
    try {
      setRows(await api.listApplications())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load applications.')
      setRows([])
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    api
      .listApplications()
      .then((data) => {
        if (!cancelled) setRows(data)
      })
      .catch(() => {
        if (!cancelled) setRows([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  const visible = useMemo(() => {
    if (!rows) return []
    const list = filter ? rows.filter((row) => row.status === filter) : rows
    // Newest activity first: a tracker is read top-down, and the row you just
    // changed should not sink below twenty others.
    return [...list].sort((a, b) => {
      const at = Date.parse(a.updated_at ?? '') || 0
      const bt = Date.parse(b.updated_at ?? '') || 0
      return bt - at
    })
  }, [rows, filter])

  const move = useCallback(
    async (id: number, status: ApplicationStatus) => {
      const previous = rows
      // Optimistic: the table is a tracking surface and a spinner on every
      // keystroke-weight change would make it feel broken. Reverted on failure
      // rather than left showing a value the server refused.
      setRows((current) =>
        (current ?? []).map((row) => (row.id === id ? { ...row, status } : row)),
      )
      setSavingId(id)
      setError('')
      try {
        const updated = await api.updateApplication(id, { status })
        setRows((current) =>
          (current ?? []).map((row) => (row.id === id ? updated : row)),
        )
      } catch (err) {
        setRows(previous)
        setError(
          err instanceof ApiError ? err.message : 'Could not update that application.',
        )
      } finally {
        setSavingId(null)
      }
    },
    [rows],
  )

  const counts = useMemo(() => {
    const tally: Partial<Record<ApplicationStatus, number>> = {}
    for (const row of rows ?? []) {
      tally[row.status] = (tally[row.status] ?? 0) + 1
    }
    return tally
  }, [rows])

  return (
    <section className="card">
      <div className="card-head">
        <h2>Application tracker</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <select
            className="stage-select"
            value={filter}
            onChange={(e) => setFilter(e.target.value as ApplicationStatus | '')}
            aria-label="Filter by stage"
          >
            <option value="">All ({rows?.length ?? 0})</option>
            {APPLICATION_STATUSES.map((status) => (
              <option key={status} value={status}>
                {LABELS[status]}
                {counts[status] ? ` (${counts[status]})` : ''}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn btn-ghost btn-icon"
            onClick={() => void load()}
            aria-label="Refresh applications"
            title="Refresh"
          >
            <IconRefresh size={16} />
          </button>
        </div>
      </div>

      <div className="card-body">
        {error ? (
          <div style={{ marginBottom: 12 }}>
            <Alert variant="danger" onDismiss={() => setError('')}>
              {error}
            </Alert>
          </div>
        ) : null}

        {rows === null ? (
          <p className="stat-hint">Loading applications…</p>
        ) : visible.length === 0 ? (
          <p className="stat-hint">
            {rows.length === 0
              ? 'No applications yet. Open a job and choose "Tailor My Resume" to start one.'
              : 'No applications match this filter.'}
          </p>
        ) : (
          <table className="apps-table">
            <caption className="visually-hidden">
              Your job applications and their current stage
            </caption>
            <thead>
              <tr>
                <th scope="col">Role</th>
                <th scope="col">Company</th>
                <th scope="col">Source</th>
                <th scope="col">Match</th>
                <th scope="col">Stage</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => {
                const job = row.job_detail
                return (
                  <tr key={row.id} className={savingId === row.id ? 'row-saving' : undefined}>
                    <td className="cell-role">
                      {job?.url ? (
                        <a href={job.url} target="_blank" rel="noreferrer noopener">
                          {job.title}
                        </a>
                      ) : (
                        (job?.title ?? 'Untitled role')
                      )}
                    </td>
                    <td className="cell-company">{job?.company ?? '—'}</td>
                    <td>
                      <span className="ats-mark ats-mark-sm" title={atsLabel(job?.source)}>
                        {atsLabel(job?.source).charAt(0).toUpperCase()}
                      </span>
                    </td>
                    <td className="cell-num">
                      {job?.match_score != null ? `${Math.round(job.match_score)}%` : '—'}
                    </td>
                    <td>
                      <span className={`stage-pill ${toneFor(row.status)}`}>
                        {savingId === row.id ? <IconCheck size={12} /> : null}
                        {LABELS[row.status]}
                      </span>
                      <label className="visually-hidden" htmlFor={`stage-${row.id}`}>
                        Stage for {job?.title ?? 'application'}
                      </label>
                      <select
                        id={`stage-${row.id}`}
                        className="stage-select"
                        value={row.status}
                        disabled={savingId === row.id}
                        onChange={(e) => void move(row.id, e.target.value as ApplicationStatus)}
                      >
                        {APPLICATION_STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {LABELS[status]}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}

export default ApplicationTracker
