import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api } from '../lib/api'
import { useAuth } from '../auth/useAuth'
import { formatDate } from '../lib/format'
import type { Resume } from '../lib/types'
import { Alert, EmptyState, Pill, Skeleton } from '../components/primitives'
import { IconCheck, IconFile, IconLogo, IconUpload, IconZap } from '../components/Icons'

const MAX_BYTES = 10 * 1024 * 1024

export function OnboardingPage() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const fileInput = useRef<HTMLInputElement>(null)

  const [resumes, setResumes] = useState<Resume[] | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)

  // The server is the source of truth for the master resume, so read it on
  // mount rather than trusting cached user state.
  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const data = await api.listResumes()
        if (!cancelled) setResumes(data)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not load your resumes.')
        setResumes([])
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const upload = useCallback(
    async (file: File) => {
      setError('')

      if (!/\.pdf$/i.test(file.name)) {
        setError('Only PDF resumes are supported.')
        return
      }
      if (file.size > MAX_BYTES) {
        setError('That file is larger than 10 MB. Please upload a smaller PDF.')
        return
      }

      setUploading(true)
      try {
        const form = new FormData()
        form.append('name', file.name.replace(/\.pdf$/i, ''))
        form.append('resume_type', 'MASTER')
        form.append('is_master', 'true')
        form.append('file', file)

        const created = await api.uploadResume(form)
        setResumes((current) => [created, ...(current ?? [])])
        await refresh()
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : 'Upload failed. The PDF may be a scanned image with no selectable text.',
        )
      } finally {
        setUploading(false)
        if (fileInput.current) fileInput.current.value = ''
      }
    },
    [refresh],
  )

  const promote = useCallback(
    async (id: number) => {
      setError('')
      try {
        await api.setMasterResume(id)
        setResumes((current) =>
          (current ?? []).map((item) => ({ ...item, is_master: item.id === id })),
        )
        await refresh()
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Could not update your master resume.')
      }
    },
    [refresh],
  )

  const master = resumes?.find((resume) => resume.is_master)

  return (
    <div className="setup-shell">
      <div className="bg-fx" aria-hidden="true" />

      <header className="setup-header">
        <span className="brand">
          <span className="brand-mark">
            <IconLogo size={19} />
          </span>
          <span className="brand-name">TailorUp</span>
        </span>
        <span className="setup-step">Master resume</span>
      </header>

      <main className="setup-main">
        <p className="eyebrow">Get started</p>
        <h1 className="setup-title">Upload your master resume</h1>
        <p className="setup-sub">
          {user?.email} · Every job you analyse is scored against this document, so TailorUp
          extracts your skills, experience, and certifications from it first.
        </p>

        {error ? (
          <div style={{ marginBottom: 18 }}>
            <Alert variant="danger" onDismiss={() => setError('')}>
              {error}
            </Alert>
          </div>
        ) : null}

        {resumes === null && !error ? (
          <Skeleton width="100%" height={190} radius={20} />
        ) : master ? (
          <div className="card animate-in">
            <div className="card-head">
              <span className="stat-icon green">
                <IconCheck size={16} />
              </span>
              <div style={{ minWidth: 0 }}>
                <h3>Master resume ready</h3>
                <p className="stat-hint">
                  {master.name} · uploaded {formatDate(master.created_at)}
                </p>
              </div>
              <div className="card-head-actions">
                <Pill tone="success">Active</Pill>
              </div>
            </div>
            <div className="card-body">
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={() => navigate('/setup/skills')}
              >
                <IconZap size={16} />
                Continue to skills
              </button>
            </div>
          </div>
        ) : (
          <div
            className={`dropzone${dragging ? ' dragging' : ''}`}
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              const file = event.dataTransfer.files?.[0]
              if (file) void upload(file)
            }}
          >
            <span className="dropzone-icon">
              <IconUpload size={22} />
            </span>
            <h3>{uploading ? 'Processing your resume…' : 'Drop your resume here'}</h3>
            <p>PDF only, up to 10 MB. Text must be selectable, not a scanned image.</p>

            <button
              type="button"
              className="btn btn-primary"
              onClick={() => fileInput.current?.click()}
              disabled={uploading}
            >
              {uploading ? <span className="spinner" /> : <IconFile size={16} />}
              {uploading ? 'Uploading…' : 'Choose a PDF'}
            </button>

            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,.pdf"
              className="visually-hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void upload(file)
              }}
            />
          </div>
        )}

        {resumes !== null && resumes.length > 0 && !master ? (
          <div className="card" style={{ marginTop: 18 }}>
            <div className="card-head">
              <h3>Your resumes</h3>
            </div>
            <div className="job-list">
              {resumes.map((resume) => (
                <div className="job-row" key={resume.id} style={{ cursor: 'default' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                    <span className="avatar avatar-lg">
                      <IconFile size={16} />
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div className="job-row-title">{resume.name}</div>
                      <div className="job-row-meta">
                        <span>{formatDate(resume.created_at)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="job-row-score">
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => void promote(resume.id)}
                    >
                      Use as master
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {resumes !== null && resumes.length === 0 && !error ? (
          <EmptyState title="No resumes yet" description="Upload a PDF to continue." />
        ) : null}
      </main>
    </div>
  )
}

export default OnboardingPage

