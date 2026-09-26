import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../lib/api'
import type {
  EntryChange,
  Job,
  Resume,
  SourceEntry,
  TailoringResponse,
  TailoringViolation,
} from '../lib/types'
import { Alert, Pill } from './primitives'

/**
 * Turn an API failure into something a person can act on.
 *
 * The brief requires distinct states for AI-unavailable, timeout, validation
 * failure, unauthorized, missing resume, missing job and a generic failure. The
 * server sends a stable `code`, so the mapping is driven by that rather than by
 * guessing from the status number.
 */
function describeFailure(error: unknown): { title: string; message: string } {
  if (!(error instanceof ApiError)) {
    return { title: 'Tailoring failed', message: 'Something went wrong. Please try again.' }
  }

  const code = (error as ApiError & { code?: string }).code

  switch (code) {
    case 'ai_unavailable':
      return {
        title: 'AI is unavailable',
        message:
          'The tailoring service could not be reached. Check that your AI provider is running, then try again.',
      }
    case 'ai_timeout':
      return {
        title: 'The AI took too long',
        message: 'The request timed out. Large resumes can be slow — try again in a moment.',
      }
    case 'ai_not_configured':
      return {
        title: 'Tailoring is not set up',
        message: 'No AI provider is configured for this deployment.',
      }
    case 'ai_validation_failed':
      return {
        title: 'Result rejected as inaccurate',
        message:
          'The generated resume claimed experience your master resume does not support, so it was discarded.',
      }
    case 'resume_missing':
      return {
        title: 'No master resume',
        message: 'Upload a master resume before tailoring one for a job.',
      }
    case 'job_missing':
      return { title: 'Job not found', message: 'This job is no longer available to you.' }
    case 'job_description_missing':
      return {
        title: 'Nothing to tailor against',
        message: 'This job has no stored description. Re-analyse it first.',
      }
    default:
      break
  }

  if (error.status === 401 || error.status === 403) {
    return { title: 'Not permitted', message: 'You do not have access to tailor this resume.' }
  }
  if (error.status === 0) {
    return { title: 'Cannot reach the API', message: 'Check that the backend is running.' }
  }
  return { title: 'Tailoring failed', message: error.message || 'Please try again.' }
}

/* ---------- Review pieces ---------- */

function Bullets({ items, tone }: { items: string[]; tone: 'before' | 'after' }) {
  if (!items.length) {
    return <p className="stat-hint">Nothing in this section.</p>
  }
  return (
    <ul className={`ba-list ba-${tone}`}>
      {items.map((item, index) => (
        <li key={`${index}-${item.slice(0, 12)}`}>{item}</li>
      ))}
    </ul>
  )
}

/** ORIGINAL vs TAILORED, with the model's stated reason underneath. */
function EntryReview({
  title,
  subtitle,
  change,
  source,
}: {
  title: string
  subtitle?: string
  change: EntryChange | undefined
  source: SourceEntry | undefined
}) {
  // Prefer our stored originals. The model echoes them back, but that echo is
  // untrusted; the server sends the real ones in `source`.
  const original = source?.bullets ?? change?.original_bullets ?? []
  const tailored = change?.tailored_bullets ?? []

  if (!change && !source) return null

  const unchanged =
    tailored.length > 0 && tailored.join(' | ') === original.join(' | ')

  return (
    <div className="ba-entry">
      <div className="ba-entry-head">
        <span className="ba-entry-title">{title}</span>
        {subtitle ? <span className="ba-entry-sub">{subtitle}</span> : null}
        {unchanged ? <Pill tone="neutral">unchanged</Pill> : <Pill tone="success">rewritten</Pill>}
      </div>

      <div className="ba-cols">
        <div className="ba-col">
          <div className="ba-col-label">Original</div>
          <Bullets items={original} tone="before" />
        </div>
        <div className="ba-col">
          <div className="ba-col-label">Tailored</div>
          <Bullets items={tailored} tone="after" />
        </div>
      </div>

      {change?.changes?.length ? (
        <details className="ba-why">
          <summary>Why this changed</summary>
          <ul>
            {change.changes.map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}

function ViolationList({ violations }: { violations: TailoringViolation[] }) {
  if (!violations.length) return null
  return (
    <div className="ba-violations">
      <div className="ba-col-label">Needs review</div>
      <ul>
        {violations.map((violation, index) => (
          <li key={`${violation.code}-${index}`}>
            <span className={`mono ba-sev ba-sev-${violation.severity}`}>{violation.code}</span>
            <span>{violation.message}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ---------- Main ---------- */

type Phase = 'idle' | 'loading' | 'review' | 'saving' | 'saved'

/**
 * "Tailor My Resume" for one job.
 *
 * Flow: button -> loading -> before/after review -> explicit save. The AI
 * output is never presented as verified: the verdict badge, the unsupported
 * requirements list and the "needs review" warnings are always visible, and
 * nothing is written until the user chooses to save.
 */
export function TailorResume({ job }: { job: Job }) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [failure, setFailure] = useState<{ title: string; message: string } | null>(null)
  const [violations, setViolations] = useState<TailoringViolation[]>([])
  const [data, setData] = useState<TailoringResponse | null>(null)
  const [saved, setSaved] = useState<Resume | null>(null)
  const [available, setAvailable] = useState<boolean | null>(null)

  // Ask once whether tailoring is configured, so the button can be disabled
  // with an explanation instead of failing on click.
  useEffect(() => {
    let cancelled = false
    api
      .tailoringStatus()
      .then((status) => {
        if (!cancelled) setAvailable(status.available)
      })
      .catch(() => {
        if (!cancelled) setAvailable(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const run = useCallback(async () => {
    setPhase('loading')
    setFailure(null)
    setViolations([])
    setSaved(null)
    try {
      const result = await api.tailorResume(job.id)
      setData(result)
      setPhase('review')
    } catch (error) {
      // Always leaves the loading state: the UI must never be stuck.
      setFailure(describeFailure(error))
      const payload = (error as ApiError & { violations?: TailoringViolation[] })?.violations
      if (payload) setViolations(payload)
      setPhase('idle')
    }
  }, [job.id])

  const save = useCallback(async () => {
    if (!data) return
    setPhase('saving')
    setFailure(null)
    try {
      const created = await api.saveTailoredResume(
        job.id,
        data.result,
        data.provider?.provider,
      )
      setSaved(created)
      setPhase('saved')
    } catch (error) {
      setFailure(describeFailure(error))
      const payload = (error as ApiError & { violations?: TailoringViolation[] })?.violations
      if (payload) setViolations(payload)
      setPhase('review')
    }
  }, [data, job.id])

  const verdict = data?.validation
  const unsupported = data?.result?.skills?.unsupported_requirements ?? []
  const sourceExperience = data?.source?.experience ?? []
  const sourceProjects = data?.source?.projects ?? []

  return (
    <div className="card-inner ba">
      <div className="ba-head">
        <div>
          <div className="section-title">Tailor my resume</div>
          <p className="stat-hint">
            Rewrites your master resume for this role. Nothing is saved until you review it.
          </p>
        </div>

        {phase === 'idle' || phase === 'review' || phase === 'saved' ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={run}
            disabled={available === false}
            title={available === false ? 'No AI provider is configured.' : undefined}
          >
            ✨ Tailor My Resume
          </button>
        ) : null}
      </div>

      {available === false ? (
        <div style={{ marginTop: 14 }}>
          <Alert variant="info">
            Tailoring is unavailable on this deployment: no AI provider is configured.
          </Alert>
        </div>
      ) : null}

      {phase === 'loading' ? (
        <div className="ba-loading" role="status" aria-live="polite">
          <span className="ba-spinner" aria-hidden="true" />
          Analyzing your resume against this job...
        </div>
      ) : null}

      {failure ? (
        <div style={{ marginTop: 14 }}>
          <Alert variant="danger" onDismiss={() => setFailure(null)}>
            <strong>{failure.title}</strong>
            <div>{failure.message}</div>
          </Alert>
        </div>
      ) : null}

      {phase === 'saved' && saved ? (
        <div style={{ marginTop: 14 }}>
          <Alert variant="success">
            Saved as a new resume: <strong>{saved.name}</strong>. Your master resume is
            unchanged.
          </Alert>
        </div>
      ) : null}

      {data && (phase === 'review' || phase === 'saving' || phase === 'saved') ? (
        <div className="ba-review">
          <div className="ba-verdict">
            {verdict?.status === 'valid' ? (
              <Pill tone="success">verified against your master resume</Pill>
            ) : (
              <Pill tone="warning">needs review</Pill>
            )}
            {data.provider?.display_name ? (
              <span className="stat-hint"> via {data.provider.display_name}</span>
            ) : null}
          </div>

          {verdict?.status === 'warning' ? (
            <Alert variant="warning">
              This rewrite was flagged for review. Check every change against your master
              resume before using it.
            </Alert>
          ) : null}

          <ViolationList violations={violations.length ? violations : verdict?.violations ?? []} />

          {data.result.summary?.tailored ? (
            <EntryReview
              title="Summary"
              change={undefined}
              source={{ id: 'summary', bullets: data.result.summary.original ? [data.result.summary.original] : [] }}
            />
          ) : null}

          {data.result.experience.map((change) => (
            <EntryReview
              key={change.entry_id}
              title="Experience"
              subtitle={change.entry_id}
              change={change}
              source={sourceExperience.find((entry) => entry.id === change.entry_id)}
            />
          ))}

          {data.result.projects.map((change) => (
            <EntryReview
              key={change.entry_id}
              title="Project"
              subtitle={change.entry_id}
              change={change}
              source={sourceProjects.find((entry) => entry.id === change.entry_id)}
            />
          ))}

          <div className="ba-skills">
            {data.result.skills.emphasized.length ? (
              <div>
                <div className="ba-col-label">Emphasised</div>
                <div className="ba-chips">
                  {data.result.skills.emphasized.map((skill) => (
                    <Pill key={skill} tone="success">
                      {skill}
                    </Pill>
                  ))}
                </div>
              </div>
            ) : null}

            {data.result.skills.deemphasized.length ? (
              <div>
                <div className="ba-col-label">De-emphasised</div>
                <div className="ba-chips">
                  {data.result.skills.deemphasized.map((skill) => (
                    <Pill key={skill} tone="neutral">
                      {skill}
                    </Pill>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          {unsupported.length ? (
            <div className="ba-unsupported">
              <div className="ba-col-label">Requirements your resume does not support</div>
              <p className="stat-hint">
                These were deliberately <em>not</em> written into the resume. Close them
                honestly, or mention them only if you can evidence them.
              </p>
              <ul>
                {unsupported.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {data.result.warnings?.length ? (
            <div className="ba-unsupported">
              <div className="ba-col-label">Warnings from the model</div>
              <ul>
                {data.result.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="ba-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={save}
              disabled={phase === 'saving'}
            >
              {phase === 'saving' ? 'Saving...' : 'Save as a new resume'}
            </button>
            <button type="button" className="btn" onClick={run} disabled={phase === 'saving'}>
              Start over
            </button>
            <span className="stat-hint">
              Saving creates a separate version. Your master resume is never overwritten.
            </span>
          </div>
        </div>
      ) : null}
    </div>
  )
}
