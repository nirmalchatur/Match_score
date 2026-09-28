import { useRef, useState } from 'react'
import { formatDate, formatScore } from '../lib/format'
import { ApiError, api } from '../lib/api'
import type { Job, Resume } from '../lib/types'
import { IconExternal, IconFile, IconRefresh, IconUpload, IconZap } from '../components/Icons'
import { Alert, EmptyState, Pill, Skeleton } from '../components/primitives'
import { DownloadButtons } from '../components/DownloadButtons'

function ResumeCard({
  resume,
  isMaster,
  job,
}: {
  resume: Resume
  isMaster: boolean
  job?: { title: string; company: string; match_score: number | null } | null
}) {
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
            <span>
              {job ? `${job.company} — ${job.title}` : `Created ${formatDate(resume.created_at)}`}
            </span>
            <Pill tone={isMaster ? 'accent' : 'neutral'}>
              {isMaster ? 'Master' : resume.resume_type}
            </Pill>
            {resume.tailoring_summary === 'warning' ? <Pill tone="warning">needs review</Pill> : null}
          </div>
          {job?.match_score != null ? (
            <div className="stat-hint">Match {formatScore(job.match_score)}</div>
          ) : null}
        </div>
      </div>

      <div className="job-row-score">
        {resume.file ? (
          <a
            className="btn btn-ghost btn-sm"
            href={api.resumeFileUrl(resume.id)}
            target="_blank"
            rel="noreferrer noopener"
          >
            Open
            <IconExternal size={14} />
          </a>
        ) : null}
        {resume.has_documents !== false ? (
          <DownloadButtons resumeId={resume.id} label="" size="sm" />
        ) : null}
      </div>
    </div>
  )
}

type Props = {
  resumes: Resume[]
  master: Resume | null
  jobs?: Job[]
  loading: boolean
  error: string
  onRefresh: () => void
}

export function ResumesPage({ resumes, master, jobs = [], loading, error, onRefresh }: Props) {
  // This page previously had no upload control at all: the "Library" card
  // described `POST /api/resumes/` in prose while `api.uploadResume` sat
  // unused, so "Manage resumes" could not actually add a resume. The only
  // working route to an upload was a browser tab running curl.
  const [file, setFile] = useState<File | null>(null)
  const [asMaster, setAsMaster] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const submitUpload = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!file || uploading) return

    setUploading(true)
    setUploadError('')
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('name', file.name.replace(/\.pdf$/i, '') || 'Resume')
      form.append('resume_type', 'MASTER')
      // A first resume is always the master: there is nothing else to score
      // against, and the API rejects a request with no master set.
      form.append('is_master', asMaster || !master ? 'true' : 'false')

      await api.uploadResume(form)
      setFile(null)
      setAsMaster(false)
      // Reset the native control too. Clearing React state does not clear the
      // input, so the same filename would silently re-upload on the next pick.
      if (fileRef.current) fileRef.current.value = ''
      onRefresh()
    } catch (err) {
      setUploadError(
        err instanceof ApiError
          ? err.message
          : 'The upload did not finish. Check the file is a readable PDF and try again.',
      )
    } finally {
      setUploading(false)
    }
  }
  // Tailored versions are split out of the flat list so the workspace reads as
  // "master + one version per job" rather than an undifferentiated pile.
  const isMaster = (resume: Resume) => resume.is_master || master?.id === resume.id
  const tailored = resumes.filter((resume) => !isMaster(resume))
  const jobById = new Map(jobs.map((job) => [job.id, job]))
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
              Upload
            </div>

            <form className="upload-form" onSubmit={submitUpload}>
              <label className="form-label" htmlFor="resume-file">
                PDF
              </label>
              <div className="upload-drop">
                <input
                  id="resume-file"
                  ref={fileRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
                {file ? (
                  <div className="upload-picked">
                    <IconFile size={16} />
                    <span className="upload-name" title={file.name}>
                      {file.name}
                    </span>
                    <span className="stat-hint">{Math.round(file.size / 1024)} KB</span>
                  </div>
                ) : (
                  <span className="stat-hint">Choose a PDF, or drop one here.</span>
                )}
              </div>

              <label className="check-row">
                <input
                  type="checkbox"
                  checked={asMaster}
                  onChange={(event) => setAsMaster(event.target.checked)}
                />
                <span>Make this the master resume</span>
              </label>

              {uploadError ? <Alert variant="danger">{uploadError}</Alert> : null}

              <button
                type="submit"
                className="btn btn-primary"
                disabled={!file || uploading}
              >
                {uploading ? <span className="spinner" /> : <IconUpload size={15} />}
                {uploading ? 'Uploading…' : 'Upload resume'}
              </button>

              <p className="stat-hint" style={{ lineHeight: 1.6 }}>
                Every job is scored against your master resume. Tailoring never overwrites it —
                each tailored version is stored separately.
              </p>
            </form>
          </div>
        </div>
      </section>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {loading ? (
        <section className="card">
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
        </section>
      ) : resumes.length === 0 ? (
        <section className="card">
          <EmptyState
            title="No resumes yet"
            description="Use the upload panel to add your first resume."
          />
        </section>
      ) : (
        <>
          <section className="card">
            <div className="card-head">
              <h3>Master resume</h3>
              <div className="card-head-actions">
                <span className="pill">{master ? 1 : 0}</span>
              </div>
            </div>
            <div className="job-list">
              {resumes.filter(isMaster).map((resume) => (
                <ResumeCard key={resume.id} resume={resume} isMaster />
              ))}
            </div>
            <p className="stat-hint" style={{ marginTop: 12 }}>
              Never overwritten. Tailoring always creates a separate version below.
            </p>
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Tailored resumes</h3>
              <div className="card-head-actions">
                <span className="pill">{tailored.length}</span>
                <button
                  type="button"
                  className="btn btn-ghost btn-icon"
                  onClick={onRefresh}
                  disabled={loading}
                  aria-label="Refresh resumes"
                  title="Refresh"
                >
                  <IconRefresh size={16} />
                </button>
              </div>
            </div>

            {tailored.length === 0 ? (
              <EmptyState
                title="No tailored versions yet"
                description="Open a job and choose “Tailor My Resume” to create a version for it."
              />
            ) : (
              <div className="job-list">
                {tailored.map((resume) => (
                  <ResumeCard
                    key={resume.id}
                    resume={resume}
                    isMaster={false}
                    job={resume.source_job ? jobById.get(resume.source_job) ?? null : null}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

export default ResumesPage
