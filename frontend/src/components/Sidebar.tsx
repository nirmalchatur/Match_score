import { useState } from 'react'
import type { Job, ViewKey } from '../lib/types'
import { initials } from '../lib/format'
import { DevTerminal } from './DevTerminal'
import {
  IconBriefcase,
  IconDashboard,
  IconFile,
  IconHelp,
  IconKanban,
  IconLogo,
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
  jobs?: Job[]
}) {
  /**
   * Signing out is destructive enough to confirm, but not so much that a
   * modal is warranted.
   *
   * The first click arms the button and the second confirms; navigating or
   * waiting disarms it. `leaving` guards the case where the click that follows
   * confirmation is the one that unmounts this component -- without it the
   * component would try to set state after unmount and React would warn.
   */
  const [confirmingLogout, setConfirmingLogout] = useState(false)
  const [leaving, setLeaving] = useState(false)

  const requestLogout = () => {
    if (leaving) return
    if (!confirmingLogout) {
      setConfirmingLogout(true)
      return
    }
    setLeaving(true)
    onLogout()
  }
  const renderItem = ({ key, label, Icon, count }: NavItem) => (
    <button
      key={key}
      type="button"
      className={`nav-item${view === key ? ' active' : ''}`}
      onClick={() => { setConfirmingLogout(false); onNavigate(key) }}
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
          <span className="brand-mark">
            <IconLogo size={17} />
          </span>
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
        <a className="nav-item" href="/docs/README.md" target="_blank" rel="noreferrer">
          <IconHelp size={17} />
          <span>Help</span>
        </a>
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
          className={`nav-item sidebar-logout${confirmingLogout ? ' confirming' : ''}`}
          onClick={requestLogout}
          onBlur={() => setConfirmingLogout(false)}
          aria-label={confirmingLogout ? 'Confirm sign out' : 'Sign out'}
          title={confirmingLogout ? 'Click again to sign out' : 'Sign out'}
        >
          <IconLogout size={17} />
          <span>{confirmingLogout ? 'Click again to sign out' : 'Sign out'}</span>
        </button>
      </div>
    </aside>
  )
}

export default Sidebar
