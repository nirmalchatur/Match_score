import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api } from '../lib/api'
import { useAuth } from '../auth/useAuth'
import { formatDate } from '../lib/format'
import type { TailoringStatus, UserProfile } from '../lib/types'
import { Alert, Pill } from '../components/primitives'
import { IconCheck, IconFile, IconLayers, IconZap } from '../components/Icons'

const DISCIPLINES = [
  { value: '', label: 'Not set' },
  { value: 'ENGINEER', label: 'Engineering' },
  { value: 'DESIGNER', label: 'Design' },
  { value: 'PRODUCT', label: 'Product' },
  { value: 'DATA', label: 'Data & Analytics' },
  { value: 'MARKETING', label: 'Marketing' },
  { value: 'OTHER', label: 'Other' },
]

export function SettingsPage() {
  const { user, logout, refresh } = useAuth()
  const navigate = useNavigate()

  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [ai, setAi] = useState<TailoringStatus | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const data = await api.getProfile()
        if (!cancelled) setProfile(data)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load your settings.')
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    // Read-only. AI configuration is server-side and is deliberately not
    // editable from the UI: there are no per-user providers, so there is
    // nothing a user could meaningfully change here.
    api
      .tailoringStatus()
      .then((status) => {
        if (!cancelled) setAi(status)
      })
      .catch(() => {
        if (!cancelled) setAi(null)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!profile || saving) return

    setSaving(true)
    setError('')
    try {
      const updated = await api.updateProfile({
        headline: profile.headline,
        discipline: profile.discipline,
        target_locations: profile.target_locations,
      })
      setProfile(updated)
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2500)
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save your settings.')
    } finally {
      setSaving(false)
    }
  }

  const patch = (key: keyof UserProfile, value: string) =>
    setProfile((current) => (current ? { ...current, [key]: value } : current))

  return (
    <div className="page stack">
      <section className="card">
        <div className="card-head">
          <h2>Account</h2>
        </div>
        <div className="card-body">
          <div className="grid-detail">
            <div className="metric">
              <span className="metric-label">Email</span>
              <span className="metric-value">{user?.email}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Name</span>
              <span className="metric-value">
                {[user?.first_name, user?.last_name].filter(Boolean).join(' ') || 'Not set'}
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Member since</span>
              <span className="metric-value">{formatDate(user?.date_joined)}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Job preferences</h2>
        </div>
        <form className="card-body" onSubmit={save}>
          {error ? (
            <div style={{ marginBottom: 16 }}>
              <Alert variant="danger" onDismiss={() => setError('')}>
                {error}
              </Alert>
            </div>
          ) : null}

          <label className="form-label" htmlFor="headline">
            Headline
          </label>
          <input
            id="headline"
            className="auth-input"
            value={profile?.headline ?? ''}
            onChange={(event) => patch('headline', event.target.value)}
            placeholder="Backend Engineer"
            disabled={!profile || saving}
          />

          <label className="form-label" htmlFor="discipline">
            Discipline
          </label>
          <select
            id="discipline"
            className="select"
            value={profile?.discipline ?? ''}
            onChange={(event) => patch('discipline', event.target.value)}
            disabled={!profile || saving}
          >
            {DISCIPLINES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <label className="form-label" htmlFor="locations">
            Target locations
          </label>
          <input
            id="locations"
            className="auth-input"
            value={profile?.target_locations ?? ''}
            onChange={(event) => patch('target_locations', event.target.value)}
            placeholder="Pune, Remote, Bengaluru"
            disabled={!profile || saving}
          />

          <div style={{ marginTop: 18 }}>
            <button type="submit" className="btn btn-primary" disabled={!profile || saving}>
              {saving ? <span className="spinner" /> : saved ? <IconCheck size={15} /> : null}
              {saving ? 'Saving…' : saved ? 'Saved' : 'Save changes'}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Master resume</h2>
          <div className="card-head-actions">
            <Pill tone={user?.has_master_resume ? 'success' : 'warning'}>
              {user?.has_master_resume ? 'Configured' : 'Missing'}
            </Pill>
          </div>
        </div>
        <div className="card-body">
          <p className="stat-hint" style={{ marginTop: 0, marginBottom: 16 }}>
            Your master resume is the document every job analysis is scored against.
          </p>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => navigate('/setup/resume')}
          >
            <IconFile size={15} />
            Manage resumes
          </button>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>AI</h2>
          <div className="card-head-actions">
            <Pill tone={ai?.available ? 'success' : 'warning'}>
              {ai?.available ? 'Ready' : 'Unavailable'}
            </Pill>
          </div>
        </div>
        <div className="card-body">
          <p className="stat-hint" style={{ marginTop: 0, lineHeight: 1.65 }}>
            Resume tailoring runs on the AI provider configured for this deployment.
            Configuration is set on the server and is shown here for reference only.
          </p>
          <div className="grid-detail" style={{ marginTop: 18 }}>
            <div className="metric">
              <span className="metric-label">Provider</span>
              <span className="metric-value">
                {ai?.available ? (ai.display_name || ai.provider || 'Configured') : 'Not configured'}
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Model</span>
              <span className="metric-value">{ai?.model || '—'}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Master resume</span>
              <span className="metric-value">
                {user?.has_master_resume ? 'Ready' : 'Missing'}
              </span>
            </div>
          </div>
          {!ai?.available ? (
            <div style={{ marginTop: 16 }}>
              <Alert variant="warning">
                Tailoring is unavailable. Ask an administrator to configure an AI provider
                on the server.
              </Alert>
            </div>
          ) : null}
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Plan</h2>
          <div className="card-head-actions">
            <Pill tone="accent">Free</Pill>
          </div>
        </div>
        <div className="card-body">
          <p className="stat-hint" style={{ marginTop: 0, lineHeight: 1.65 }}>
            TailorUp is currently in its foundation release. Usage limits and paid plans are not
            enabled yet — you have unrestricted access to every feature that exists today.
          </p>
          <div className="grid-detail" style={{ marginTop: 18 }}>
            <div className="metric">
              <span className="metric-label">Jobs analysed</span>
              <span className="metric-value">{user?.job_count ?? 0}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Usage limit</span>
              <span className="metric-value">
                <IconLayers size={14} style={{ display: 'inline' }} /> Unlimited
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Billing</span>
              <span className="metric-value">
                <IconZap size={14} style={{ display: 'inline' }} /> Not enabled
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Session</h2>
        </div>
        <div className="card-body">
          <p className="stat-hint" style={{ marginTop: 0, marginBottom: 16 }}>
            Sign out of TailorUp on this device.
          </p>
          <button
            type="button"
            className="btn btn-danger"
            onClick={async () => {
              await logout()
              navigate('/', { replace: true })
            }}
          >
            Sign out
          </button>
        </div>
      </section>
    </div>
  )
}

export default SettingsPage

