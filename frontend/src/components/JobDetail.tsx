import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { Application, ApplicationStatus, Job, JobSummary } from '../lib/types'
import { formatDate, formatScore, scoreTone, sourceHost, statusLabel, statusTone } from '../lib/format'
import { IconExternal, IconMapPin } from './Icons'
import { Alert, Pill, ScoreRing, Skeleton } from './primitives'
import { StepList } from './StepList'
import { TailorResume } from './TailorResume'
import { SkillGapPanel } from './SkillGapPanel'
import { ApplicationPanel } from './ApplicationPanel'

/**
 * Full rows already fetched, keyed by job id.
 *
 * Module scope rather than component state, so moving up and down the list does
 * not refetch the same posting every time the user clicks back to it. The
 * cached row carries ``updated_at`` and is only reused while that still matches
 * the row in the list, so a re-analysis -- or the shell's own refresh -- 
 * invalidates it with no cache-busting call to remember.
 */
const detailCache = new Map<number, Job>()

type Props = {
  /** The compact list row. The posting itself is fetched on selection. */
  job: JobSummary
  application?: Application | null
  onCreateApplication?: () => Promise<unknown>
  onApplicationStatus?: (id: number, status: ApplicationStatus) => Promise<unknown>
  onDeleteApplication?: (id: number) => Promise<unknown>
}

export function JobDetail({
  job,
  application = null,
  onCreateApplication,
  onApplicationStatus,
  onDeleteApplication,
}: Props) {
  const [detail, setDetail] = useState<Job | null>(() => detailCache.get(job.id) ?? null)
  const [detailError, setDetailError] = useState('')
  const [loadedId, setLoadedId] = useState(job.id)

  // Reset to the newly selected job *during render*, which is React's documented
  // pattern for state derived from a prop. Doing it in the effect instead would
  // call setState synchronously on mount and start a second render for every
  // selection -- and rendering the previous job's posting under the new job's
  // title, even for one frame, is worse than a skeleton.
  if (loadedId !== job.id) {
    const cached = detailCache.get(job.id)
    setLoadedId(job.id)
    setDetail(cached && cached.updated_at === job.updated_at ? cached : null)
    setDetailError('')
  }

  /**
   * Fetch the full row for the selected job.
   *
   * The list no longer carries the posting, the stored analysis or the skill
   * gap: sending those for every job made the dashboard's job payload 2.0 MB at
   * 400 rows, which is what stalled the page. One row on selection is the same
   * data for a request that costs a fraction.
   */
  useEffect(() => {
    const cached = detailCache.get(job.id)
    if (cached && cached.updated_at === job.updated_at) return

    const controller = new AbortController()

    api
      .getJob(job.id, controller.signal)
      .then((full) => {
        if (controller.signal.aborted) return
        detailCache.set(job.id, full)
        setDetail(full)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setDetailError(err instanceof Error ? err.message : 'Could not load this job.')
      })

    return () => controller.abort()
  }, [job.id, job.updated_at])

  const tone = statusTone(job.status)
  const host = sourceHost(job.url)

  return (
    <div className="card animate-in">
      <div className="card-head">
        <div style={{ minWidth: 0 }}>
          <p className="eyebrow">Job analysis</p>
          <h2 style={{ marginTop: 4 }}>{job.title || 'Untitled role'}</h2>
        </div>
        <div className="card-head-actions">
          <Pill tone={tone} live={tone === 'warning'}>
            {statusLabel(job.status)}
          </Pill>
        </div>
      </div>

      <div className="card-body">
        {/* Headline match score */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 18,
            padding: 18,
            marginBottom: 20,
            borderRadius: 'var(--r-lg)',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
          }}
        >
          <ScoreRing score={job.match_score} size={74} />
          <div style={{ minWidth: 0 }}>
            <div className="metric-label">Overall match score</div>
            <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.03em' }}>
              {formatScore(job.match_score)}
            </div>
            <div className="stat-hint">
              {job.match_score == null
                ? 'Scoring has not run yet.'
                : scoreTone(job.match_score) === 'success'
                  ? 'Strong alignment with your master resume.'
                  : scoreTone(job.match_score) === 'warning'
                    ? 'Partial alignment — review the gaps below.'
                    : 'Low alignment — tailor your resume before applying.'}
            </div>
          </div>
        </div>

        <div style={{ marginBottom: 20 }}>
          {detail ? (
            <SkillGapPanel gap={detail.skill_gap} />
          ) : detailError ? (
            <p className="stat-hint">
              The skill gap for this job could not be loaded. Its score above is
              unaffected.
            </p>
          ) : (
            <div className="stack" style={{ gap: 8 }}>
              <Skeleton width="30%" height={12} />
              <Skeleton width="70%" height={12} />
            </div>
          )}
        </div>

        {/* Key facts */}
        <div className="grid-detail" style={{ marginBottom: 20 }}>
          <div className="metric">
            <span className="metric-label">Company</span>
            <span className="metric-value">{job.company || 'Unknown'}</span>
          </div>
          <div className="metric">
            <span className="metric-label">Location</span>
            <span className="metric-value" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <IconMapPin size={14} />
              {job.location || 'Remote'}
            </span>
          </div>
          <div className="metric">
            <span className="metric-label">Source</span>
            <span className="metric-value" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {host || '—'}
              {job.url ? (
                <a
                  href={job.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="metric-value"
                  aria-label="Open original job posting"
                  style={{ display: 'inline-flex' }}
                >
                  <IconExternal size={14} />
                </a>
              ) : null}
            </span>
          </div>
        </div>

        {detail?.error_message ? (
          <div style={{ marginBottom: 20 }}>
            <Alert variant="danger">{detail.error_message}</Alert>
          </div>
        ) : null}

        <div className="divider" />

        <TailorResume job={job} />

        <div className="divider" />

        {onCreateApplication && onApplicationStatus ? (
          <>
            <ApplicationPanel
              application={application}
              onCreate={onCreateApplication}
              onStatusChange={onApplicationStatus}
              onDelete={onDeleteApplication}
            />
            <div className="divider" />
          </>
        ) : null}

        <StepList steps={detail?.pipeline_steps} updatedAt={job.updated_at} />

        <div className="divider" />

        <div className="section-title">Job information</div>
        {detail ? (
          detail.description?.trim() ? (
            <div className="prose prose-scroll">{detail.description}</div>
          ) : (
            <p className="stat-hint">No description was extracted for this posting.</p>
          )
        ) : detailError ? (
          <p className="stat-hint">
            The posting text could not be loaded. The analysis above was already
            sent with the list and is not affected.
          </p>
        ) : (
          <div className="stack" style={{ gap: 10 }}>
            <Skeleton width="90%" height={12} />
            <Skeleton width="80%" height={12} />
            <Skeleton width="60%" height={12} />
          </div>
        )}

        {job.created_at ? (
          <div className="stat-hint" style={{ marginTop: 16 }}>
            Analyzed {formatDate(job.created_at)}
          </div>
        ) : null}
      </div>
    </div>
  )
}
