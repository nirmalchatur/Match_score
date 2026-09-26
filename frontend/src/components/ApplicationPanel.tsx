import { useState } from 'react'
import { ApiError } from '../lib/api'
import {
  APPLICATION_STATUSES,
  STATUS_LABELS,
  type Application,
  type ApplicationStatus,
} from '../lib/types'
import { Alert } from './primitives'

/**
 * The application section of a job: create one, and move it through the
 * pipeline.
 *
 * Creating an application starts it at **Saved**, never at Applied. Tailoring a
 * resume is not applying, and inferring otherwise would put a false record in
 * the user's tracker.
 */
export function ApplicationPanel({
  application,
  onCreate,
  onStatusChange,
  onDelete,
}: {
  application: Application | null
  onCreate: () => Promise<unknown>
  onStatusChange: (id: number, status: ApplicationStatus) => Promise<unknown>
  onDelete?: (id: number) => Promise<unknown>
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Every path clears `busy` in a finally block, so the controls can never be
  // left disabled after a failure.
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Something went wrong. Please try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  if (!application) {
    return (
      <div className="ba-inner">
        <div className="section-title">Application</div>
        <p className="stat-hint" style={{ marginTop: 6, marginBottom: 12 }}>
          Not tracked yet. Save this job to follow it through your pipeline.
        </p>
        {error ? <Alert variant="danger">{error}</Alert> : null}
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => run(onCreate)}
        >
          {busy ? <span className="spinner" /> : null}
          Save Job
        </button>
      </div>
    )
  }

  return (
    <div className="ba-inner">
      <div className="section-title">Application</div>

      <div className="ap-row" style={{ marginTop: 12 }}>
        <span className="stat-hint">Status</span>
        <span className={`ap-status ap-${application.status.toLowerCase()}`}>
          {STATUS_LABELS[application.status]}
        </span>
      </div>

      {application.applied_at ? (
        <div className="ap-row">
          <span className="stat-hint">Applied</span>
          <span className="ap-value">
            {new Date(application.applied_at).toLocaleDateString()}
          </span>
        </div>
      ) : null}

      {error ? (
        <div style={{ marginTop: 10 }}>
          <Alert variant="danger">{error}</Alert>
        </div>
      ) : null}

      <div className="ap-actions" style={{ marginTop: 14 }}>
        <label className="ap-field">
          <span className="metric-label">Change status</span>
          <select
            className="ap-select"
            value={application.status}
            disabled={busy}
            onChange={(event) =>
              void run(() => onStatusChange(application.id, event.target.value as ApplicationStatus))
            }
          >
            {APPLICATION_STATUSES.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </label>

        {application.status === 'SAVED' ? (
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => void run(() => onStatusChange(application.id, 'APPLIED'))}
          >
            Mark as Applied
          </button>
        ) : null}

        {onDelete ? (
          <button
            type="button"
            className="btn btn-ghost"
            disabled={busy}
            onClick={() => void run(() => onDelete(application.id))}
          >
            Remove
          </button>
        ) : null}
      </div>
    </div>
  )
}
