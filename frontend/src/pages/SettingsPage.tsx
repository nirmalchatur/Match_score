import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api } from '../lib/api'
import { useAuth } from '../auth/useAuth'
import { formatDate } from '../lib/format'
import type { AiKeyStatus, TailoringStatus, UserProfile } from '../lib/types'
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

  // The signed-in user's own key. `keyValue` is the only place the plaintext
  // exists on the client, and it is cleared the moment the save resolves.
  const [keyStatus, setKeyStatus] = useState<AiKeyStatus | null>(null)
  const [keyValue, setKeyValue] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [editingKey, setEditingKey] = useState(false)
  const [keySaving, setKeySaving] = useState(false)
  const [keyError, setKeyError] = useState('')

  /**
   * Whether tailoring will actually work for this account right now.
   *
   * A configured provider is not sufficient: a bring-your-own-key provider
   * also needs *this* user to have saved a key. Treating "the deployment has
   * Gemini" as "tailoring works" is what produced a button that failed for
   * everyone who had not pasted a key yet.
   */
  const aiReady = ai?.requires_user_key
    ? Boolean(ai?.user_key_configured)
    : Boolean(ai?.available)

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

    // Provider metadata plus this account's key status. Both are needed to
    // decide whether the tailoring button should be enabled, so they are read
    // together rather than leaving the button briefly wrong.
    Promise.allSettled([api.tailoringStatus(), api.getAiKey()])
      .then(([statusResult, keyResult]) => {
        if (cancelled) return
        if (statusResult.status === 'fulfilled') setAi(statusResult.value)
        if (keyResult.status === 'fulfilled') setKeyStatus(keyResult.value)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const submitKey = async (event: React.FormEvent) => {
    event.preventDefault()
    if (keySaving) return

    const key = keyValue.trim()
    if (!key) return

    setKeySaving(true)
    setKeyError('')
    try {
      const status = await api.saveAiKey(key)
      setKeyStatus(status)
      setEditingKey(false)
      // Drop the plaintext from component state the moment it is stored. There
      // is no way to read it back, so holding it longer serves no purpose.
      setKeyValue('')
      setShowKey(false)
      // Re-read provider status so the pill reflects the new key.
      api.tailoringStatus().then(setAi).catch(() => undefined)
    } catch (err) {
      setKeyError(err instanceof ApiError ? err.message : 'Could not save your API key.')
    } finally {
      setKeySaving(false)
    }
  }

  const removeKey = async () => {
    if (keySaving) return
    setKeySaving(true)
    setKeyError('')
    try {
      const status = await api.deleteAiKey()
      setKeyStatus(status)
      setKeyValue('')
      setEditingKey(false)
      api.tailoringStatus().then(setAi).catch(() => undefined)
    } catch (err) {
      setKeyError(err instanceof ApiError ? err.message : 'Could not remove your API key.')
    } finally {
      setKeySaving(false)
    }
  }

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
            <Pill tone={aiReady ? 'success' : 'warning'}>
              {aiReady ? 'Ready' : 'Needs a key'}
            </Pill>
          </div>
        </div>
        <div className="card-body">
          <p className="stat-hint" style={{ marginTop: 0, lineHeight: 1.65 }}>
            Resume tailoring runs on <strong>Google Gemini</strong>. Add your own free API key
            below to enable it — TailorUp never ships one, and the key is yours alone.
          </p>

          <div className="grid-detail" style={{ marginTop: 18 }}>
            <div className="metric">
              <span className="metric-label">Provider</span>
              <span className="metric-value">
                {ai?.display_name || ai?.provider || 'Not configured'}
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Model</span>
              <span className="metric-value">{ai?.model || '—'}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Your key</span>
              <span className="metric-value">
                {keyStatus?.configured ? (
                  <span className="key-hint">{keyStatus.key_hint}</span>
                ) : (
                  'Not added'
                )}
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Master resume</span>
              <span className="metric-value">
                {user?.has_master_resume ? 'Ready' : 'Missing'}
              </span>
            </div>
          </div>

          {!ai?.available && ai?.provider !== 'gemini' ? (
            <div style={{ marginTop: 16 }}>
              <Alert variant="warning">
                Tailoring is unavailable. This deployment has no AI provider configured — ask an
                administrator to set one on the server.
              </Alert>
            </div>
          ) : null}

          {/* Only offered for a bring-your-own-key provider. For a local Ollama
              setup there is no key to add, and showing the form would mislead. */}
          {ai?.requires_user_key ? (
            <div style={{ marginTop: 20 }}>
              {keyStatus?.configured && !editingKey ? (
                <>
                  <Alert variant="success">
                    Your API key is saved and tailoring is ready to use.
                  </Alert>
                  <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn"
                      onClick={() => {
                        setEditingKey(true)
                        setKeyValue('')
                        setKeyError('')
                      }}
                    >
                      Replace key
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={removeKey}
                      disabled={keySaving}
                    >
                      {keySaving ? 'Removing…' : 'Remove key'}
                    </button>
                  </div>
                </>
              ) : (
                <form onSubmit={submitKey} className="stack" style={{ gap: 12 }}>
                  {keyStatus?.configured ? (
                    <Alert variant="info">Enter a new key to replace the saved one.</Alert>
                  ) : null}

                  <label className="form-label" htmlFor="ai-api-key">
                    Google AI Studio API key
                  </label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      id="ai-api-key"
                      className="input-field"
                      type={showKey ? 'text' : 'password'}
                      value={keyValue}
                      onChange={(e) => setKeyValue(e.target.value)}
                      placeholder="AIza…"
                      autoComplete="off"
                      spellCheck={false}
                      maxLength={200}
                      /* A key is a credential: keep it out of autofill,
                         session-restore and password-manager paths, all of
                         which would otherwise retain it in the browser. */
                      name="ai-api-key"
                      data-lpignore="true"
                      data-1p-ignore="true"
                    />
                    <button
                      type="button"
                      className="btn"
                      onClick={() => setShowKey((v) => !v)}
                      aria-label={showKey ? 'Hide API key' : 'Show API key'}
                    >
                      {showKey ? 'Hide' : 'Show'}
                    </button>
                  </div>

                  <p className="stat-hint" style={{ margin: 0, lineHeight: 1.6 }}>
                    Create a free key at{' '}
                    <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">
                      Google AI Studio
                    </a>
                    . It is stored encrypted, never shown again, and deleted when you sign out.
                  </p>

                  {keyError ? <Alert variant="danger">{keyError}</Alert> : null}

                  <div style={{ display: 'flex', gap: 10 }}>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      disabled={keySaving || !keyValue.trim()}
                    >
                      {keySaving ? 'Saving…' : 'Save key'}
                    </button>
                    {keyStatus?.configured ? (
                      <button
                        type="button"
                        className="btn"
                        onClick={() => setEditingKey(false)}
                        disabled={keySaving}
                      >
                        Cancel
                      </button>
                    ) : null}
                  </div>
                </form>
              )}
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

