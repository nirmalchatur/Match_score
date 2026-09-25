import { formatDate } from '../lib/format'
import { api } from '../lib/api'
import type { Resume } from '../lib/types'
import { IconExternal, IconFile, IconRefresh, IconUpload, IconZap } from '../components/Icons'
import { Alert, EmptyState, Pill, Skeleton } from '../components/primitives'

function ResumeCard({ resume, isMaster }: { resume: Resume; isMaster: boolean }) {
  return (
    <div className="job-row" style={{ cursor: 'default' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
        <span className="avatar avatar-lg">
          <IconFile size={18} />
        </span>
        <div style={{ minWidth: 0 }}>
          <div className="job-row-title" title={resume.name}>
            {resume.name}
          </div>
          <div className="job-row-meta">
            <span>{formatDate(resume.created_at)}</span>
            <Pill tone={isMaster ? 'accent' : 'neutral'}>
              {isMaster ? 'Master' : resume.resume_type}
            </Pill>
          </div>
        </div>
      </div>

      <div className="job-row-score">
        {resume.file ? (
          <a
            className="btn btn-ghost btn-sm"
            href={api.fileUrl(resume.file)}
            target="_blank"
            rel="noreferrer noopener"
          >
            Open
            <IconExternal size={14} />
          </a>
        ) : null}
      </div>
    </div>
  )
}

type Props = {
  resumes: Resume[]
  master: Resume | null
  loading: boolean
  error: string
  onRefresh: () => void
}

export function ResumesPage({ resumes, master, loading, error, onRefresh }: Props) {
  return (
    <div className="page stack">
      <section className="grid-two">
        <div className="card">
          <div className="card-body">
            <div className="section-title">
              <IconZap size={13} />
              Master resume
            </div>
            {loading ? (
              <div style={{ display: 'grid', gap: 8 }}>
                <Skeleton width="60%" height={18} />
                <Skeleton width="35%" height={12} />
              </div>
            ) : master ? (
              <>
                <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.02em' }}>
                  {master.name}
                </div>
                <p className="stat-hint" style={{ marginTop: 6 }}>
                  Every job is scored against this resume. Uploaded{' '}
                  {formatDate(master.created_at)}.
                </p>
              </>
            ) : (
              <Alert variant="warning">
                No master resume is set. Job scoring will fail until one is uploaded through the API.
              </Alert>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-body">
            <div className="section-title">
              <IconUpload size={13} />
              Library
            </div>
            <p className="stat-hint" style={{ marginTop: 0, lineHeight: 1.65 }}>
              Upload resumes with{' '}
              <code className="mono" style={{ fontSize: 12 }}>
                POST /api/resumes/
              </code>{' '}
              — send the PDF as multipart form data with <code className="mono">name</code>,{' '}
              <code className="mono">resume_type</code>, and <code className="mono">is_master</code>.
            </p>
          </div>
        </div>
      </section>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <section className="card">
        <div className="card-head">
          <h3>All resumes</h3>
          <div className="card-head-actions">
            <span className="pill">{loading ? '—' : resumes.length}</span>
            <button
              type="button"
              className="btn btn-ghost btn-icon"
              onClick={onRefresh}
              disabled={loading}
              aria-label="Refresh resumes"
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
                <Skeleton width={42} height={42} radius={12} />
                <div style={{ flex: 1, display: 'grid', gap: 7 }}>
                  <Skeleton width="45%" />
                  <Skeleton width="28%" height={11} />
                </div>
              </div>
            ))}
          </div>
        ) : resumes.length === 0 ? (
          <EmptyState
            title="No resumes yet"
            description="Upload a master resume so MatchScore can start scoring job descriptions."
          />
        ) : (
          <div className="job-list">
            {resumes.map((resume) => (
              <ResumeCard
                key={resume.id}
                resume={resume}
                isMaster={resume.is_master || master?.id === resume.id}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default ResumesPage
