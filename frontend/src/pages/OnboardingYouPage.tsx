import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert } from '../components/primitives'
import { IconCheck, IconLogo } from '../components/Icons'
import { ApiError, api } from '../lib/api'
import type { CareerStage } from '../lib/types'

/**
 * Onboarding step 3: who are you?
 *
 * Three stages, and years of experience only for the one where it means
 * something. A final-year student and a fresher are genuinely different
 * situations, so they are not collapsed into one option.
 *
 * The cross-field rule ("professional implies at least one year") is enforced
 * on the server; the inline error here is so the user is not made to submit to
 * discover it.
 */
const STAGES: { value: CareerStage; title: string; body: string }[] = [
  {
    value: 'student',
    title: 'Student',
    body: 'Studying now, or between terms. Projects and coursework count.',
  },
  {
    value: 'fresher',
    title: 'Fresher',
    body: 'Graduated and looking for a first role. Internships count.',
  },
  {
    value: 'professional',
    title: 'Working professional',
    body: 'Already in the field, with real years behind you.',
  },
]

export function OnboardingYouPage() {
  const navigate = useNavigate()

  const [stage, setStage] = useState<CareerStage | ''>('')
  const [years, setYears] = useState(1)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let cancelled = false

    api
      .getProfile()
      .then((data) => {
        if (cancelled) return
        setStage((data.career_stage as CareerStage) ?? '')
        if (data.years_experience) setYears(data.years_experience)
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(
          err instanceof ApiError ? err.message : 'Could not load your profile.',
        )
      })

    return () => {
      cancelled = true
    }
  }, [])

  const needsYears = stage === 'professional'
  const canSave = stage !== '' && (!needsYears || years >= 1)

  const save = useCallback(async () => {
    if (!canSave || saving) return
    setSaving(true)
    setError('')
    try {
      // Only send what the step owns. Sending the whole profile would risk
      // overwriting a headline the user set elsewhere with a stale copy.
      await api.updateProfile({
        career_stage: stage,
        years_experience: needsYears ? years : 0,
      })
      navigate('/setup/ai')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save your answers.')
    } finally {
      setSaving(false)
    }
  }, [canSave, saving, stage, years, needsYears, navigate])

  if (loadError) {
    return (
      <div className="setup-shell">
        <div className="setup-main">
          <Alert variant="danger">{loadError}</Alert>
        </div>
      </div>
    )
  }

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
        <span className="mono">Step 3 of 4</span>
      </header>

      <main className="setup-main">
        <span className="eyebrow">About you</span>
        <h1>Which describes you best?</h1>
        <p className="prose" style={{ marginBottom: 22 }}>
          This changes how roles are described to you, and how much experience a
          posting is expected to ask for.
        </p>

        {error ? (
          <div style={{ marginBottom: 18 }}>
            <Alert variant="danger" onDismiss={() => setError('')}>
              {error}
            </Alert>
          </div>
        ) : null}

        {STAGES.map((option) => {
          const isOn = stage === option.value
          return (
            <button
              key={option.value}
              type="button"
              className={`card choice-card${isOn ? ' selected' : ''}`}
              aria-pressed={isOn}
              onClick={() => setStage(option.value)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                marginBottom: 12,
                cursor: 'pointer',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  marginBottom: 4,
                }}
              >
                {isOn ? <IconCheck size={16} /> : null}
                <strong>{option.title}</strong>
              </div>
              <span className="stat-hint">{option.body}</span>
            </button>
          )
        })}

        {needsYears ? (
          <div className="card" style={{ margin: '18px 0' }}>
            <div className="card-body">
              <label className="form-label" htmlFor="years">
                Years of work experience
              </label>
              <input
                id="years"
                type="number"
                min={1}
                max={60}
                value={years}
                onChange={(event) => setYears(Number(event.target.value) || 0)}
                style={{ width: 120 }}
              />
              <p className="stat-hint" style={{ marginTop: 8 }}>
                Count internships and part-time work if you want them included.
              </p>
            </div>
          </div>
        ) : null}

        <button
          type="button"
          className="btn btn-primary btn-block"
          onClick={() => void save()}
          disabled={!canSave || saving}
        >
          {saving ? <span className="spinner" /> : null}
          {saving ? 'Saving…' : 'Continue'}
        </button>
      </main>
    </div>
  )
}

export default OnboardingYouPage
