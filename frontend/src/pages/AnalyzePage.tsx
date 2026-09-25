import type { Job } from '../lib/types'
import { IconLink, IconRadar, IconTarget, IconZap } from '../components/Icons'
import { JobDetail } from '../components/JobDetail'
import { UrlForm } from '../components/UrlForm'
import { Alert } from '../components/primitives'

const STAGES = [
  {
    Icon: IconLink,
    title: 'Collect',
    body: 'Fetches the posting from the Greenhouse board and pulls out company, title, and location.',
  },
  {
    Icon: IconRadar,
    title: 'Parse',
    body: 'Cleans the job description and extracts the required skills, seniority, and responsibilities.',
  },
  {
    Icon: IconTarget,
    title: 'Match',
    body: 'Scores the role against your master resume and records how each requirement aligned.',
  },
]

type Props = {
  analyzing: boolean
  error: string
  result: Job | null
  onAnalyze: (url: string) => void
}

export function AnalyzePage({ analyzing, error, result, onAnalyze }: Props) {
  return (
    <div className="page stack">
      <section className="card">
        <div className="card-body">
          <div className="section-title">
            <IconZap size={13} />
            Job URL
          </div>
          <p className="prose" style={{ marginBottom: 16 }}>
            Paste a Greenhouse job link. The pipeline collects the posting, parses the description,
            and scores it against your master resume.
          </p>
          <UrlForm onSubmit={onAnalyze} busy={analyzing} />
        </div>
      </section>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {result ? <JobDetail job={result} /> : null}

      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
          gap: 16,
        }}
      >
        {STAGES.map(({ Icon, title, body }) => (
          <div className="stat-boxed" key={title}>
            <span className="stat-icon">
              <Icon size={16} />
            </span>
            <div className="stat-label" style={{ marginBottom: 8 }}>
              {title}
            </div>
            <p className="stat-hint" style={{ marginTop: 0, lineHeight: 1.6 }}>
              {body}
            </p>
          </div>
        ))}
      </section>
    </div>
  )
}
