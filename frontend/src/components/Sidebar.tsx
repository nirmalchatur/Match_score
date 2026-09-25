import type { ViewKey } from '../lib/types'
import { initials } from '../lib/format'
import {
  IconBriefcase,
  IconDashboard,
  IconFile,
  IconHelp,
  IconKanban,
  IconLogo,
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
}: {
  view: ViewKey
  onNavigate: (view: ViewKey) => void
  jobCount: number
  email: string
  displayName: string
}) {
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
      </nav>

      <div className="sidebar-footer">
        <div className="user-chip">
          <span className="user-avatar">{initials(displayName || email)}</span>
          <span className="user-meta">
            <span className="user-name">{displayName || 'Your account'}</span>
            <span className="user-email">{email}</span>
          </span>
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
