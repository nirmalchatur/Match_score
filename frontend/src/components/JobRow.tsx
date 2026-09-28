import { formatRelative, initials, statusLabel, statusTone } from '../lib/format'
import type { Job } from '../lib/types'
import { IconClock, IconMapPin } from './Icons'
import { AtsMark } from './AtsBadge'
import { Pill, ScoreRing } from './primitives'

export function JobRow({
  job,
  selected = false,
  onSelect,
}: {
  job: Job
  selected?: boolean
  onSelect: (job: Job) => void
}) {
  const tone = statusTone(job.status)
  const isLive = tone === 'warning'

  return (
    <button
      type="button"
      className={`job-row${selected ? ' selected' : ''}`}
      onClick={() => onSelect(job)}
      aria-pressed={selected}
    >
      <div style={{ minWidth: 0 }}>
        <div className="job-row-title" title={job.title}>
          {job.title || 'Untitled role'}
        </div>
        <div className="job-row-meta">
          <AtsMark source={job.source} />
          <span className="avatar" aria-hidden="true">
            {initials(job.company)}
          </span>
          <span>{job.company || 'Unknown company'}</span>
          {job.location ? (
            <span>
              <IconMapPin size={12} />
              {job.location}
            </span>
          ) : null}
          {job.created_at ? (
            <span title={job.created_at}>
              <IconClock size={12} />
              {formatRelative(job.created_at)}
            </span>
          ) : null}
        </div>
      </div>

      <div className="job-row-score">
        <Pill tone={tone} live={isLive}>
          {statusLabel(job.status)}
        </Pill>
        <ScoreRing score={job.match_score} size={42} />
      </div>
    </button>
  )
}
