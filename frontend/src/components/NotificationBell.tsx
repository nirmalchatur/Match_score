import { useCallback, useEffect, useRef, useState } from 'react'
import { api, isAuthError } from '../lib/api'
import type { Notification, NotificationKind } from '../lib/types'
import { IconBell, IconCheck, IconClose } from './Icons'

/**
 * The unread dot.
 *
 * Rendered only when there is something unread. A grey "0" badge is noise: it
 * tells the user nothing and makes a real count harder to spot.
 */
function UnreadDot({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span className="bell-dot" aria-hidden="true">
      {count > 9 ? '9+' : count}
    </span>
  )
}

/** Relative time, falling back to an empty string rather than "Invalid Date". */
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`
  return new Date(then).toLocaleDateString()
}

const KIND_TONE: Record<NotificationKind, string> = {
  INFO: 'bell-item-info',
  SUCCESS: 'bell-item-success',
  WARNING: 'bell-item-warning',
  ERROR: 'bell-item-error',
}

/**
 * The notification bell.
 *
 * This was previously a static `<span>` holding an icon: no click handler, no
 * endpoint, no state. The backend it now talks to is `apps.automation`, which
 * did not exist before either.
 *
 * Polling, not websockets. Django on Render runs behind gunicorn with no
 * channel layer configured, so a socket would either fail to connect or land
 * on a different worker than the one holding the request. A poll on an
 * interval is honest about that constraint.
 *
 * Pausing matters: a hidden tab is the clearest signal the user is not looking
 * at the badge, and polling a Render free instance while hidden wastes a
 * wake-up. The list re-fetches on return to visible, so pausing loses nothing.
 */
export function NotificationBell({
  onNavigate,
}: {
  onNavigate?: (path: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<Notification[]>([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const containerRef = useRef<HTMLDivElement | null>(null)
  // In a ref so the Escape and outside-click handlers can read the current
  // value without being torn down and re-registered on every render.
  const openRef = useRef(false)

  const load = useCallback(async () => {
    try {
      const data = await api.listNotifications()
      setItems(data.results)
      setUnread(data.unread_count)
      setError('')
    } catch (err) {
      // A failed poll is not worth a banner. The badge keeps the count it had
      // and the next tick retries; showing an error would flash red at a user
      // who did nothing wrong.
      if (isAuthError(err)) return
      setError('Could not load notifications.')
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load, then a background poll.
  useEffect(() => {
    setLoading(true)
    void load()

    const tick = () => {
      if (document.hidden) return
      void load()
    }
    const onVisible = () => {
      if (!document.hidden) void load()
    }

    const timer = window.setInterval(tick, 60_000)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [load])

  // Close on outside click and on Escape.
  //
  // Both are accessibility requirements rather than polish: a popover that only
  // closes on an outside click is a trap for anyone navigating by keyboard, and
  // leaving focus inside a subtree that is about to unmount breaks tab order.
  useEffect(() => {
    if (!open) return

    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      const trigger = containerRef.current?.querySelector('.bell-button')
      if (trigger instanceof HTMLElement) trigger.focus()
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const toggle = () => {
    const next = !openRef.current
    openRef.current = next
    setOpen(next)
    if (next) {
      setLoading(true)
      void load()
    }
  }

  const markAllRead = async () => {
    try {
      const result = await api.markAllNotificationsRead()
      setUnread(0)
      // Trust the server's count over the rows we happen to hold. Only the
      // first page is fetched, so a large backlog would otherwise leave a
      // stale badge with no visible row explaining it.
      if (result.updated > 0) {
        setItems((current) => current.map((row) => ({ ...row, is_read: true })))
      }
    } catch {
      setError('Could not mark everything as read.')
    }
  }

  const openItem = async (row: Notification) => {
    if (!row.is_read) {
      // Optimistic: the row is marked immediately and reverts if the call
      // fails. Waiting for a round trip to clear a dot makes the popover feel
      // broken on a slow connection, and the revert covers the failure case.
      setItems((current) =>
        current.map((item) =>
          item.id === row.id ? { ...item, is_read: true } : item,
        ),
      )
      setUnread((count) => Math.max(0, count - 1))
      try {
        await api.markNotificationRead(row.id)
      } catch {
        setItems((current) =>
          current.map((item) =>
            item.id === row.id ? { ...item, is_read: false } : item,
          ),
        )
        setUnread((count) => count + 1)
      }
    }

    if (row.link) {
      onNavigate?.(row.link)
      setOpen(false)
    }
  }

  return (
    <div className="bell-wrap" ref={containerRef}>
      <button
        type="button"
        className="bell bell-button"
        onClick={toggle}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
      >
        <IconBell size={18} />
        <UnreadDot count={unread} />
      </button>

      {open ? (
        <div className="bell-popover" role="dialog" aria-label="Notifications">
          <div className="bell-head">
            <strong>Notifications</strong>
            {unread > 0 ? (
              <button type="button" className="bell-link" onClick={markAllRead}>
                <IconCheck size={14} />
                Mark all read
              </button>
            ) : null}
          </div>

          {error ? <p className="bell-error">{error}</p> : null}

          {loading && items.length === 0 ? (
            <p className="bell-empty">Loading...</p>
          ) : null}

          {!loading && items.length === 0 && !error ? (
            <p className="bell-empty">
              Nothing yet. Analyses and application updates will show up here.
            </p>
          ) : null}

          <ul className="bell-list">
            {items.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  className={[
                    'bell-item',
                    KIND_TONE[row.kind],
                    row.is_read ? 'bell-item-read' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => void openItem(row)}
                >
                  <span className="bell-item-title">
                    {row.title}
                    {row.is_read ? null : (
                      <span className="bell-unread-mark" aria-label="Unread" />
                    )}
                  </span>
                  {row.body ? (
                    <span className="bell-item-body">{row.body}</span>
                  ) : null}
                  <span className="bell-item-time">
                    {relativeTime(row.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          <div className="bell-foot">
            <button
              type="button"
              className="bell-link"
              onClick={() => setOpen(false)}
            >
              <IconClose size={14} />
              Close
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default NotificationBell
