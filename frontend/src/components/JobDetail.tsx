import type { Job } from '../lib/types'
import { formatDate, formatScore, scoreTone, sourceHost, statusLabel, statusTone } from '../lib/format'
import { IconExternal, IconMapPin } from './Icons'
import { Alert, Pill, ScoreRing } from './primitives'
import { StepList } from './StepList'

export function JobDetail({ job }: { job: Job }) {
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

        {job.error_message ? (
          <div style={{ marginBottom: 20 }}>
            <Alert variant="danger">{job.error_message}</Alert>
          </div>
        ) : null}

        <StepList steps={job.pipeline_steps} updatedAt={job.updated_at} />

        <div className="divider" />

        <div className="section-title">Job information</div>
        {job.description?.trim() ? (
          <div className="prose prose-scroll">{job.description}</div>
        ) : (
          <p className="stat-hint">No description was extracted for this posting.</p>
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
