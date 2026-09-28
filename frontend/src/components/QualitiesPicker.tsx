import { useEffect, useMemo, useState } from 'react'
import { Alert, Pill } from './primitives'
import { ApiError, api } from '../lib/api'
import type { QualityKind, QualitiesResponse, QualitySelection } from '../lib/types'

/**
 * The qualities picker.
 *
 * Why it is a picker and not a free-text box
 * ------------------------------------------
 * These values are compared against job descriptions. "great with people" and
 * "cross-functional collaboration" are the same idea written two ways, and
 * neither would match a posting that says "strong stakeholder communication".
 * A fixed catalogue is what lets the match analysis and the tailoring prompt
 * treat a selection as something it can reason about.
 *
 * The catalogue and the minimum are fetched, not hard-coded, so this component
 * cannot drift from what the server accepts. See the note on
 * :type:`QualitiesResponse`.
 *
 * The minimum is checked here for the sake of a usable button, and again on
 * the server, which is the control that actually counts.
 */
export function QualitiesPicker() {
  const [data, setData] = useState<QualitiesResponse | null>(null)
  const [selected, setSelected] = useState<QualitySelection | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
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
          err instanceof ApiError ? err.message : 'Could not load the qualities picker.'
        )
      })

    return () => {
      cancelled = true
    }
  }, [])

  const count = useMemo(
    () => (selected ? Object.values(selected).reduce((sum, list) => sum + list.length, 0) : 0),
    [selected]
  )

  const minimum = data?.minimum_total ?? 7
  // Mirrors the server rule: the total alone is not enough, every category has
  // to contribute or the other two are decorative.
  const emptyKinds = data
    ? data.kinds.filter((kind) => (selected?.[kind] ?? []).length === 0)
    : []
  const ready = count >= minimum && emptyKinds.length === 0

  const toggle = (kind: QualityKind, value: string) => {
    setSaved(false)
    setSelected((current) => {
      if (!current) return current
      const list = current[kind] ?? []
      const next = list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
      return { ...current, [kind]: next }
    })
  }

  const save = async () => {
    if (!selected || saving || !ready) return
    setSaving(true)
    setError('')
    try {
      const result = await api.saveQualities(selected)
      setData(result)
      // Adopt the server's canonical ordering rather than the local one, so
      // what is on screen is exactly what was stored.
      setSelected(result.qualities)
      setSaved(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save your qualities.')
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <div className="card-inner">
        <Alert variant="danger">{loadError}</Alert>
      </div>
    )
  }

  if (!data || !selected) {
    return (
      <div className="card-inner">
        <p className="stat-hint">Loading qualities…</p>
      </div>
    )
  }

  return (
    <div className="card-inner">
      <p className="stat-hint">
        Pick the strengths you want a tailored resume to lead with. These change what is
        emphasised — they never add experience you have not already listed.
      </p>

      <div className="ba-head" style={{ marginTop: 14 }}>
        <Pill tone={ready ? 'success' : 'warning'}>
          {count} selected · {minimum} required
        </Pill>
      </div>

      {!ready ? (
        <div style={{ marginTop: 12 }}>
          <Alert variant="info">
            {count < minimum
              ? `Choose at least ${minimum - count} more.`
              : `Choose at least one from ${data.labels[emptyKinds[0]].toLowerCase()}.`}
          </Alert>
        </div>
      ) : null}

      {error ? (
        <div style={{ marginTop: 12 }}>
          <Alert variant="danger" onDismiss={() => setError('')}>
            {error}
          </Alert>
        </div>
      ) : null}

      {saved && !error ? (
        <div style={{ marginTop: 12 }}>
          <Alert variant="success" onDismiss={() => setSaved(false)}>
            Saved.
          </Alert>
        </div>
      ) : null}

      {data.kinds.map((kind) => (
        <div key={kind} style={{ marginTop: 18 }}>
          <div className="ba-col-label">{data.labels[kind]}</div>
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
                  {option}
                </button>
              )
            })}
          </div>
        </div>
      ))}

      <div style={{ marginTop: 18 }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={save}
          disabled={!ready || saving}
          title={!ready ? `Select at least ${minimum} qualities.` : undefined}
        >
          {saving ? 'Saving…' : 'Save qualities'}
        </button>
      </div>
    </div>
  )
}
