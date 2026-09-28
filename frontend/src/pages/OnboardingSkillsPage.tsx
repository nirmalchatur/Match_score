import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert } from '../components/primitives'
import { IconCheck, IconLogo } from '../components/Icons'
import { ApiError, api } from '../lib/api'
import type { QualityKind, QualitiesResponse, QualitySelection } from '../lib/types'

/**
 * Onboarding step 2: pick seven of twenty-five.
 *
 * The catalogue and the minimum are fetched rather than hard-coded, so this
 * component cannot drift from what the server accepts -- see the note on
 * :type:`QualitiesResponse`.
 *
 * The server enforces the minimum of seven. The disabled button here is a
 * courtesy so the user is not made to discover the rule by being rejected.
 */
export function OnboardingSkillsPage() {
  const navigate = useNavigate()

  const [data, setData] = useState<QualitiesResponse | null>(null)
  const [selected, setSelected] = useState<QualitySelection | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let cancelled = false

    api
      .getQualities()
      .then((result) => {
        if (cancelled) return
        setData(result)
        setSelected(result.qualities)
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(
          err instanceof ApiError ? err.message : 'Could not load the skills list.',
        )
      })

    return () => {
      cancelled = true
    }
  }, [])

  const count = selected
    ? (Object.values(selected) as string[][]).reduce((sum, list) => sum + list.length, 0)
    : 0

  const minimum = data?.minimum_total ?? 7
  const ready = count >= minimum
  // Not blocking. Seven areas and a minimum of seven means "one from each" is
  // really "exactly one from each", which would oblige a backend engineer to
  // claim an HR skill they do not have. The gaps are surfaced, not enforced.
  //
  // Derived from `selected`, NOT from `data.uncovered_groups`. That server
  // field only changes on save -- and this page navigates away the moment the
  // save succeeds -- so reading it left the banner claiming all seven areas
  // were empty no matter what the user had picked. `data` carries the
  // catalogue and the rules; `selected` is the live answer.
  const gaps = (data?.kinds ?? []).filter(
    (kind) => (selected?.[kind] ?? []).length === 0,
  )

  const toggle = useCallback((kind: QualityKind, value: string) => {
    setError('')
    setSelected((current) => {
      if (!current) return current
      const list = current[kind] ?? []
      const next = list.includes(value)
        ? list.filter((item) => item !== value)
        : [...list, value]
      return { ...current, [kind]: next }
    })
  }, [])

  const save = useCallback(async () => {
    if (!selected || saving || !ready) return
    setSaving(true)
    setError('')
    try {
      const result = await api.saveQualities(selected)
      setSelected(result.qualities)
      setData(result)
      navigate('/setup/you')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save your skills.')
    } finally {
      setSaving(false)
    }
  }, [selected, saving, ready, navigate])

  if (loadError) {
    return (
      <div className="setup-shell">
        <div className="setup-main">
          <Alert variant="danger">{loadError}</Alert>
        </div>
      </div>
    )
  }

  if (!data || !selected) {
    return (
      <div className="setup-shell">
        <div className="setup-main">
          <p className="prose">Loading skills…</p>
        </div>
      </div>
    )
  }

  const totalOptions = Object.values(data.catalogue).flat().length

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
        <span className="mono">Step 2 of 4</span>
      </header>

      <main className="setup-main">
        <span className="eyebrow">Your strengths</span>
        <h1>Choose {minimum} skills</h1>
        <p className="prose" style={{ marginBottom: 22 }}>
          Pick {minimum} of the {totalOptions} below. These tell a tailored resume
          which of your strengths to lead with — they never add experience you have
          not already listed.
        </p>

        <div
          className="stat-hint"
          style={{ marginBottom: 20, fontWeight: 600 }}
        >
          {count} of {minimum} selected
        </div>

        {gaps.length > 0 && count > 0 ? (
          <div style={{ marginBottom: 18 }}>
            <Alert variant="info">
              {gaps.length === data.kinds.length
                ? 'Nothing selected in any area yet.'
                : `No pick yet in ${gaps.length} of ${data.kinds.length} areas: ${gaps
                    .map((kind) => data.labels[kind])
                    .join(', ')}.`}
              {ready ? ' You can save as it is -- a rounded profile is not required.' : ''}
            </Alert>
          </div>
        ) : null}

        {error ? (
          <div style={{ marginBottom: 18 }}>
            <Alert variant="danger" onDismiss={() => setError('')}>
              {error}
            </Alert>
          </div>
        ) : null}

        {data.kinds.map((kind) => (
          <section key={kind} className="card" style={{ marginBottom: 14 }}>
            <div className="card-head">
              <h3>{data.labels[kind]}</h3>
            </div>
            <div className="card-body">
              <div className="ba-chips">
                {data.catalogue[kind].map((option) => {
                  const isOn = (selected[kind] ?? []).includes(option)
                  return (
                    <button
                      key={option}
                      type="button"
                      className={isOn ? 'btn btn-primary' : 'btn'}
                      aria-pressed={isOn}
                      onClick={() => toggle(kind, option)}
                      style={{ margin: '0 6px 6px 0' }}
                    >
                      {isOn ? <IconCheck size={14} /> : null}
                      {option}
                    </button>
                  )
                })}
              </div>
            </div>
          </section>
        ))}

        <button
          type="button"
          className="btn btn-primary btn-block"
          onClick={() => void save()}
          disabled={!ready || saving}
        >
          {saving ? <span className="spinner" /> : null}
          {saving ? 'Saving…' : `Continue with ${count} selected`}
        </button>
      </main>
    </div>
  )
}

export default OnboardingSkillsPage
