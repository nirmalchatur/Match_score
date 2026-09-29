import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../lib/api'
import type { AiKeyStatus, TailoringStatus } from '../lib/types'
import { IconKey, IconLock } from './Icons'

/**
 * The "API key" control in the top bar.
 *
 * What it promises, and what the code does:
 *
 * - The key is **encrypted at rest** (Fernet, keyed off SECRET_KEY). A stolen
 *   database dump does not contain it.
 * - The key is **yours**, not the deployment's. One key on the server would
 *   mean every user spends the owner's quota.
 * - The key is **deleted when you sign out**. That is not a setting, it is
 *   what the logout endpoint does, and the copy below says so because it is
 *   the reason a shared or borrowed machine is safe.
 *
 * What it does *not* promise: it cannot protect the key from code running on
 * this server, which can decrypt it by design. Saying "secure" without that
 * would be the marketing kind of secure.
 */
export function ApiKeyButton() {
  const [status, setStatus] = useState<AiKeyStatus | null>(null)
  const [providerStatus, setProviderStatus] = useState<TailoringStatus | null>(null)
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api
      .getAiKey()
      .then((result) => {
        if (!cancelled) setStatus(result)
      })
      .catch(() => {
        /* A provider that needs no key, or a transient failure: the button
           simply stays in its "unconfigured" state rather than blocking the
           page with an error nobody can act on. */
      })
    api
      .tailoringStatus()
      .then((result) => {
        if (!cancelled) setProviderStatus(result)
      })
      .catch(() => {
        /* Same reasoning. The deployment-key state is an enhancement to the
           copy here, not something the control depends on. */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const configured = Boolean(status?.configured)
  // The deployment can pay for calls on this user's behalf. Their own key
  // still wins when they have one -- see apps.ai.selection.resolve_api_key --
  // so this is not "we are ignoring your key", it is "you do not have to
  // provide one to use this".
  const appKeyAvailable = Boolean(providerStatus?.deployment_key_configured)

  const save = useCallback(async () => {
    const key = value.trim()
    if (!key || busy) return
    setBusy(true)
    setError('')
    try {
      const result = await api.saveAiKey(key)
      setStatus(result)
      // The plaintext is dropped immediately. There is no way to read it
      // back, so holding it in state serves no purpose.
      setValue('')
      setOpen(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save that key.')
    } finally {
      setBusy(false)
    }
  }, [value, busy])

  const remove = useCallback(async () => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      setStatus(await api.deleteAiKey())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not remove that key.')
    } finally {
      setBusy(false)
    }
  }, [busy])

  return (
    <div className="key-wrap">
      <button
        type="button"
        className={`btn key-btn${configured ? ' is-on' : ''}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        title={
          configured
            ? `API key saved (${status?.key_hint ?? 'hidden'})`
            : appKeyAvailable
              ? 'Using the app’s key — add your own to use yours instead'
              : 'Add your Gemini API key'
        }
      >
        {configured ? <IconKey size={15} /> : <IconLock size={15} />}
        {configured ? 'Key saved' : appKeyAvailable ? 'App key' : 'Add API key'}
      </button>

      {open ? (
        <>
          <div className="key-scrim" onClick={() => setOpen(false)} aria-hidden="true" />
          <div className="key-pop" role="dialog" aria-label="Gemini API key">
            <div className="key-pop-head">
              <strong>{configured ? 'Your API key' : 'Add your API key'}</strong>
            </div>

            {configured ? (
              <>
                <p className="stat-hint key-note">
                  A key is saved ({status?.key_hint}). It is used instead of the
                  app’s.
                </p>
                <div className="key-actions">
                  <button type="button" className="btn btn-sm" onClick={() => void remove()} disabled={busy}>
                    Remove key
                  </button>
                  <button type="button" className="btn btn-sm" onClick={() => setOpen(false)}>
                    Close
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="stat-hint key-note">
                  Get a free key from Google AI Studio, then paste it here. Your key
                  is used in preference to the app’s, so nothing you run is billed
                  to the app owner.
                </p>
                <input
                  type="password"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  placeholder="AIza..."
                  aria-label="Gemini API key"
                  autoComplete="off"
                  spellCheck={false}
                />
                {error ? (
                  <p className="key-err" role="alert">
                    {error}
                  </p>
                ) : null}
                <div className="key-actions">
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => void save()}
                    disabled={!value.trim() || busy}
                  >
                    {busy ? 'Saving…' : 'Save key'}
                  </button>
                  <button type="button" className="btn btn-sm" onClick={() => setOpen(false)}>
                    Cancel
                  </button>
                </div>
              </>
            )}

            {/* The promise, stated where the user is being asked to trust us. */}
            <p className="key-trust">
              <IconLock size={13} />
              <span>
                Encrypted on the server, never shown again, and{' '}
                <strong>deleted automatically when you sign out</strong>.
              </span>
            </p>
            <p className="key-fine">
              Need a local model instead? <Link to="/app/settings">Switch to Ollama</Link> in
              Settings.
            </p>
          </div>
        </>
      ) : null}
    </div>
  )
}

export default ApiKeyButton
