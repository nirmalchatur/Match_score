import { useState } from 'react'
import type { JobSummary, ViewKey } from '../lib/types'
import { initials } from '../lib/format'
import { DevTerminal } from './DevTerminal'
import { HelpPanel } from './HelpPanel'
import {
  BrandMark,
  IconBriefcase,
  IconDashboard,
  IconFile,
  IconHelp,
  IconKanban,
  IconLogout,
  IconRadar,
  IconSettings,
} from './Icons'

type NavItem = {
  key: ViewKey
  label: string
  Icon: typeof IconDashboard
  count?: number
}

const PRIMARY: NavItem[] = [
  { key: 'dashboard', label: 'Dashboard', Icon: IconDashboard },
  { key: 'jobs', label: 'Jobs', Icon: IconBriefcase },
  { key: 'resumes', label: 'Resumes', Icon: IconFile },
  { key: 'applications', label: 'Applications', Icon: IconKanban },
]

// Rendered below a divider, matching the reference sidebar grouping.
const SECONDARY: NavItem[] = [
  { key: 'analyze', label: 'Analyze Job', Icon: IconRadar },
  { key: 'settings', label: 'Settings', Icon: IconSettings },
]

export function Sidebar({
  view,
  onNavigate,
  jobCount,
  email,
  displayName,
  onLogout,
  jobs,
}: {
  view: ViewKey
  onNavigate: (view: ViewKey) => void
  jobCount: number
  email: string
  displayName: string
  onLogout: () => void
  jobs?: JobSummary[]
}) {
  /**
   * Signing out used to be a two-click confirm: the first click rewrote the
   * label to "Click again to sign out", the second acted on it.
   *
   * That is the worst of both patterns. It is not a real confirmation, because
   * nothing is *shown* -- the label changes and a hurried second click lands on
   * a button that used to say something else. And it disarms on blur, so a
   * click that starts elsewhere and ends here can fire it outright.
   *
   * Replaced with a real dialog: an explicit, described choice with Cancel and
   * Sign out, focus moved into it, Escape to dismiss. `leaving` guards the
   * click that unmounts this component, which would otherwise warn React.
   */
  const [confirmingLogout, setConfirmingLogout] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  const requestLogout = () => {
    if (leaving) return
    setConfirmingLogout(true)
  }
  const renderItem = ({ key, label, Icon, count }: NavItem) => (
    <button
      key={key}
      type="button"
      className={`nav-item${view === key ? ' active' : ''}`}
      onClick={() => onNavigate(key)}
      aria-current={view === key ? 'page' : undefined}
      title={label}
    >
      <Icon size={17} />
      <span>{label}</span>
      {count != null && count > 0 ? <span className="nav-count">{count}</span> : null}
    </button>
  )

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand">
          <BrandMark size={22} className="brand-emblem" />
          <span className="brand-name">TailorUp</span>
        </span>
      </div>

      <nav className="nav" aria-label="Main navigation">
        {PRIMARY.map((item) =>
          renderItem({ ...item, count: item.key === 'jobs' ? jobCount : 0 }),
        )}
        <div className="nav-divider" />
        {SECONDARY.map(renderItem)}
        <div className="nav-divider" />
        {/* Was an <a href="/docs/README.md">. The frontend is a static Vite
            bundle and serves nothing under /docs, so that link asked the app
            host for a Markdown file that is not there and 404'd. The docs live
            in the repository, not in the deployment, so the reference material
            is rendered in-app instead. */}
        <button
          type="button"
          className="nav-item"
          onClick={() => setHelpOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={helpOpen}
        >
          <IconHelp size={17} />
          <span>Help</span>
        </button>
        <DevTerminal jobs={jobs} />
      </nav>

      <div className="sidebar-footer">
        <div className="user-chip">
          <span className="user-avatar">{initials(displayName || email)}</span>
          <span className="user-meta">
            <span className="user-name">{displayName || 'Your account'}</span>
            <span className="user-email">{email}</span>
          </span>
        </div>

        <button
          type="button"
          className="nav-item sidebar-logout"
          onClick={requestLogout}
          aria-haspopup="dialog"
        >
          <IconLogout size={17} />
          <span>Sign out</span>
        </button>
      </div>

      {confirmingLogout ? (
        <div
          className="confirm-scrim"
          role="dialog"
          aria-modal="true"
          aria-labelledby="signout-title"
          onClick={(event) => {
            if (event.target === event.currentTarget) setConfirmingLogout(false)
          }}
        >
          <div className="confirm-card">
            <h2 id="signout-title" className="confirm-title">
              Sign out of TailorUp?
            </h2>
            <p className="confirm-body">
              Your saved API key is removed from this server when you sign out, and you will need
              to paste it again to use tailoring.
            </p>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setConfirmingLogout(false)}
                autoFocus
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  setLeaving(true)
                  onLogout()
                }}
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <HelpPanel open={helpOpen} onClose={() => setHelpOpen(false)} />
    </aside>
  )
}

export default Sidebar
