import { useState } from 'react'
import { IconLink, IconZap } from './Icons'

/**
 * The placeholder is a real ATS posting rather than a bare pattern.
 *
 * It used to be a Greenhouse URL, which read as "this box only accepts
 * Greenhouse" even though the server never enforced that. Now that any board
 * is accepted, the example says so.
 */
const PLACEHOLDER = 'Paste any job link — Greenhouse, Workday, Lever, or a company careers page'

/** Basic URL sanity check so obviously-bad input never hits the network. */
function isValidUrl(value: string): boolean {
  try {
    const parsed = new URL(value.trim())
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

export function UrlForm({
  onSubmit,
  busy,
}: {
  onSubmit: (url: string) => void
  busy: boolean
}) {
  const [url, setUrl] = useState('')
  const [touched, setTouched] = useState(false)

  const trimmed = url.trim()
  const invalid = touched && trimmed.length > 0 && !isValidUrl(trimmed)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    setTouched(true)
    if (!isValidUrl(trimmed) || busy) return
    onSubmit(trimmed)
  }

  return (
    <form className="form-row" onSubmit={submit} noValidate>
      <div className="field">
        <IconLink size={17} />
        <input
          type="url"
          value={url}
          onChange={(event) => {
            setUrl(event.target.value)
            setTouched(true)
          }}
          onBlur={() => setTouched(true)}
          placeholder={PLACEHOLDER}
          aria-label="Job posting URL"
          aria-invalid={invalid}
          aria-describedby={invalid ? 'url-error' : undefined}
          autoComplete="off"
          spellCheck={false}
          disabled={busy}
        />
      </div>

      <button type="submit" className="btn btn-primary" disabled={busy}>
        {busy ? <span className="spinner" /> : <IconZap size={16} />}
        {busy ? 'Analyzing…' : 'Analyze Job'}
      </button>

      {invalid ? (
        <span id="url-error" style={{ flexBasis: '100%', fontSize: 12, color: 'var(--danger)' }}>
          Enter a full http(s) URL.
        </span>
      ) : null}
    </form>
  )
}
