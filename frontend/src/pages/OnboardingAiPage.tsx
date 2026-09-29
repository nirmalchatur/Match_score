import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert } from '../components/primitives'
import { IconCheck, IconLogo } from '../components/Icons'
import { ApiError, api } from '../lib/api'
import type { AiSetup } from '../lib/types'

/**
 * Onboarding step 4: how should tailoring run?
 *
 * Two real options rather than an abstract "configure AI":
 *
 * - **Local (Ollama).** Nothing leaves the machine and there is no key, but it
 *   needs a desktop with enough RAM for a model and someone willing to follow
 *   the setup. Documented inline so the step is actionable rather than a
 *   dead end.
 * - **Hosted (Gemini AI Studio).** The free tier, no setup at all, and the key
 *   is the user's own -- stored encrypted and deleted on sign-out.
 *
 * This records the *choice* so the docs and Settings can point at the right
 * instructions. It deliberately does not change the server's ``AI_PROVIDER``,
 * which is a deployment setting: a hosted instance cannot start a local Ollama
 * daemon on the user's behalf.
 */
const OPTIONS: {
  value: AiSetup
  title: string
  body: string
  points: string[]
  docs: string
}[] = [
  {
    value: 'ollama',
    title: 'Run a model on my own machine',
    body: 'Nothing is sent anywhere and no API key is needed. Needs a desktop with roughly 8 GB of free memory.',
    points: [
      'ollama serve',
      'ollama pull llama3.1',
      'AI_PROVIDER=ollama',
    ],
    docs: 'Full instructions: docs/AI_SETUP.md in the repository',
  },
  {
    value: 'gemini',
    title: 'Use the hosted Gemini tier',
    body: 'Fast and no cost for normal use. Uses this app’s key if you have not added your own, which you can paste in Settings → AI.',
    points: [
      'Add your own key at aistudio.google.com/apikey',
      'Otherwise the app’s key is used',
      'AI_PROVIDER=gemini on the server',
    ],
    docs: 'Full instructions: docs/AI_SETUP.md in the repository',
  },
  {
    value: 'groq',
    title: 'Use Groq (fastest)',
    body: 'The quickest hosted option — the same rewrite usually returns in seconds rather than a minute. Uses this app’s key if you have not added your own.',
    points: [
      'Add your own key at console.groq.com/keys',
      'Otherwise the app’s key is used',
      'AI_PROVIDER=groq on the server',
    ],
    docs: 'Full instructions: docs/AI_SETUP.md in the repository',
  },
]

export function OnboardingAiPage() {
  const navigate = useNavigate()

  const [choice, setChoice] = useState<AiSetup | ''>('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let cancelled = false
    api
      .getProfile()
      .then((data) => {
        if (!cancelled && data.ai_setup) setChoice(data.ai_setup as AiSetup)
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadError(
            err instanceof ApiError ? err.message : 'Could not load your profile.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const finish = useCallback(async () => {
    if (!choice || saving) return
    setSaving(true)
    setError('')
    try {
      await api.updateProfile({ ai_setup: choice })
      // A local model needs no key, so there is nothing left to collect. A
      // hosted option may work immediately on the deployment's own key, so
      // Settings is offered rather than forced -- the user can add their own
      // there and skip it entirely.
      navigate(choice === 'ollama' ? '/app/dashboard' : '/app/settings')
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not save your choice.',
      )
    } finally {
      setSaving(false)
    }
  }, [choice, saving, navigate])

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
        <span className="mono">Step 4 of 4</span>
      </header>

      <main className="setup-main">
        <span className="eyebrow">How tailoring runs</span>
        <h1>Choose how AI runs</h1>
        <p className="prose" style={{ marginBottom: 22 }}>
          Resume tailoring needs a language model. Pick where it runs. You can
          change this later in Settings.
        </p>

        {error ? (
          <div style={{ marginBottom: 18 }}>
            <Alert variant="danger" onDismiss={() => setError('')}>
              {error}
            </Alert>
          </div>
        ) : null}

        {OPTIONS.map((option) => {
          const isOn = choice === option.value
          return (
            <button
              key={option.value}
              type="button"
              className={`card choice-card${isOn ? ' selected' : ''}`}
              aria-pressed={isOn}
              onClick={() => setChoice(option.value)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                marginBottom: 14,
                cursor: 'pointer',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  marginBottom: 6,
                }}
              >
                {isOn ? <IconCheck size={16} /> : null}
                <strong>{option.title}</strong>
              </div>
              <p className="stat-hint" style={{ marginTop: 0, lineHeight: 1.6 }}>
                {option.body}
              </p>
              <pre className="mono" style={{ margin: '10px 0 8px' }}>
                {option.points.join('\n')}
              </pre>
              <span className="stat-hint">{option.docs}</span>
            </button>
          )
        })}

        <button
          type="button"
          className="btn btn-primary btn-block"
          onClick={() => void finish()}
          disabled={!choice || saving}
        >
          {saving ? <span className="spinner" /> : null}
          {saving ? 'Saving…' : 'Finish setup'}
        </button>
      </main>
    </div>
  )
}

export default OnboardingAiPage
