import { useCallback, useEffect, useState } from 'react'
import { api, isAuthError } from '../lib/api'
import type { SecurityOverview } from '../lib/types'

/**
 * A readable label for a user agent string.
 *
 * Best-effort only, and deliberately not exhaustive. The full string stays in
 * the DOM as a title attribute, so an unrecognised one is still available on
 * hover rather than being hidden. Guessing beyond the three below produces
 * confident wrong answers, which is worse than saying "unknown browser".
 */
function describeAgent(agent: string): string {
  if (!agent) return 'Unknown device'

  const browser = /Firefox\//.test(agent)
    ? 'Firefox'
    : /Edg\//.test(agent)
      ? 'Edge'
      : /Chrome\//.test(agent)
        ? 'Chrome'
        : /Safari\//.test(agent)
          ? 'Safari'
          : 'Unknown browser'

  const platform = /Windows/.test(agent)
    ? 'Windows'
    : /Mac OS X|Macintosh/.test(agent)
      ? 'macOS'
      : /Android/.test(agent)
        ? 'Android'
        : /iPhone|iPad/.test(agent)
          ? 'iOS'
          : /Linux/.test(agent)
            ? 'Linux'
            : 'Unknown OS'

  return `${browser} on ${platform}`
}

function formatWhen(iso: string | null): string {
  if (!iso) return ''
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return ''
  return then.toLocaleString()
}

/**
 * Sessions, recent events, and the two actions a user takes when they suspect
 * a credential is compromised.
 *
 * "Sign out other sessions" is the primary action and sits above the fold,
 * because it is the one that works immediately and cannot lock you out. The
 * password form is below it and requires the current password, which is
 * deliberate: an unlocked browser session must not be enough to take the
 * account over permanently.
 */
export function SecurityPanel() {
  const [data, setData] = useState<SecurityOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [saving, setSaving] = useState(false)
  const [revoking, setRevoking] = useState(false)

  const load = useCallback(async () => {
    try {
      setData(await api.getSecurityOverview())
      setError('')
    } catch (err) {
      if (isAuthError(err)) return
      setError('Could not load your security information.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const onRevoke = async () => {
    setRevoking(true)
    setNotice('')
    setError('')
    try {
      const result = await api.revokeOtherSessions()
      setNotice(
        result.revoked > 0
          ? `Signed out ${result.revoked} other session${result.revoked === 1 ? '' : 's'}.`
          : 'There were no other sessions to sign out.',
      )
      await load()
    } catch {
      setError('Could not sign out other sessions. Try again.')
    } finally {
      setRevoking(false)
    }
  }

  const onChangePassword = async (event: React.FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setNotice('')
    setError('')
    try {
      await api.changePassword(current, next)
      setNotice('Password changed. You are still signed in here.')
      // Cleared rather than kept: leaving the old password in a field after a
      // successful change is how it ends up in a screenshot.
      setCurrent('')
      setNext('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change password.')
    } finally {
      setSaving(false)
    }
  }

  const others = data ? data.sessions.filter((s) => !s.is_current).length : 0

  return (
    <div className="sec">
      {error ? <p className="sec-error">{error}</p> : null}
      {notice ? <p className="sec-notice">{notice}</p> : null}

      <section className="sec-block">
        <div className="sec-head">
          <div>
            <h3>Where you are signed in</h3>
            <p className="sec-hint">
              {others > 0
                ? `This account is open on ${others} other device${others === 1 ? '' : 's'}.`
                : 'This account is only open on this device.'}
            </p>
          </div>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void onRevoke()}
            disabled={revoking || others === 0}
          >
            {revoking ? <span className="spinner" /> : null}
            Sign out other sessions
          </button>
        </div>

        {loading ? <p className="sec-muted">Loading...</p> : null}

        {data && data.sessions.length ? (
          <ul className="sec-list">
            {data.sessions.map((session) => (
              <li
                key={session.key}
                className={session.is_current ? 'sec-item sec-item-current' : 'sec-item'}
              >
                <div className="sec-item-main">
                  <strong>{describeAgent(session.user_agent)}</strong>
                  {session.is_current ? (
                    <span className="sec-badge">This device</span>
                  ) : null}
                </div>
                <div className="sec-item-meta">
                  {session.login_at ? (
                    <span>Signed in {formatWhen(session.login_at)}</span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : null}

        {!loading && data && data.sessions.length === 0 ? (
          <p className="sec-muted">No active sessions were found.</p>
        ) : null}
      </section>

      <section className="sec-block">
        <div className="sec-head">
          <div>
            <h3>Change password</h3>
            <p className="sec-hint">You will stay signed in on this device.</p>
          </div>
        </div>

        <form className="sec-form" onSubmit={onChangePassword}>
          <div className="sec-field">
            <label htmlFor="sec-current">Current password</label>
            <input
              id="sec-current"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </div>

          <div className="sec-field">
            <label htmlFor="sec-next">New password</label>
            <input
              id="sec-next"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={saving || !current || !next}
          >
            {saving ? <span className="spinner" /> : null}
            Change password
          </button>
        </form>
      </section>

      {data && data.events.length ? (
        <section className="sec-block">
          <div className="sec-head">
            <div>
              <h3>Recent activity</h3>
              <p className="sec-hint">Sign-ins and security changes on this account.</p>
            </div>
          </div>

          <ul className="sec-list">
            {data.events.map((row) => (
              <li key={row.id} className="sec-item">
                <div className="sec-item-main">
                  <strong>{row.label}</strong>
                  {row.is_current_session ? (
                    <span className="sec-badge">This device</span>
                  ) : null}
                </div>
                <div className="sec-item-meta">
                  <span>{formatWhen(row.created_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}

export default SecurityPanel
