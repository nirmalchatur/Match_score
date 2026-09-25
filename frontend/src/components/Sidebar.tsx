import type { ViewKey } from '../lib/types'
import {
  IconBriefcase,
  IconDashboard,
  IconFile,
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
  { key: 'analyze', label: 'Analyze Job', Icon: IconRadar },
]

const SECONDARY: NavItem[] = [
  { key: 'jobs', label: 'Jobs', Icon: IconBriefcase },
  { key: 'resumes', label: 'Resumes', Icon: IconFile },
  { key: 'settings', label: 'Settings', Icon: IconSettings },
]

export function Sidebar({
  view,
  onNavigate,
  jobCount,
  online,
}: {
  view: ViewKey
  onNavigate: (view: ViewKey) => void
  jobCount: number
  online: boolean
}) {
  const renderItem = ({ key, label, Icon, count }: NavItem) => (
    <button
      key={key}
      type="button"
      className={`nav-item${view === key ? ' active' : ''}`}
      onClick={() => onNavigate(key)}
      aria-current={view === key ? 'page' : undefined}
    >
      <Icon size={18} />
      <span>{label}</span>
      {count != null && count > 0 ? <span className="nav-count">{count}</span> : null}
    </button>
  )

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">
          <IconLogo size={19} />
        </span>
        <span className="brand-name">MatchScore</span>
      </div>

      <nav className="nav" aria-label="Main navigation">
        {PRIMARY.map(renderItem)}
        <div className="nav-label">Library</div>
        {SECONDARY.map((item) => renderItem({ ...item, count: item.key === 'jobs' ? jobCount : 0 }))}
      </nav>

      <div className="sidebar-footer">
        <div className="api-status">
          <span className={`api-dot ${online ? 'online' : 'offline'}`} />
          <div>
            <strong>{online ? 'API connected' : 'API offline'}</strong>
            <span className="mono" style={{ fontSize: 11 }}>
              Django · :8000
            </span>
          </div>
        </div>
      </div>
    </aside>
  )
}
