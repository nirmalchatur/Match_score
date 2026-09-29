import type { ReactNode } from 'react'
import { initials } from '../lib/format'
import NotificationBell from './NotificationBell'
import { IconSearch } from './Icons'
import ThemeToggle from './ThemeToggle'

export function Topbar({
  title,
  search,
  searchValue,
  onSearchChange,
  avatarLabel,
  actions,
  onNavigate,
}: {
  title?: string
  search?: string
  searchValue?: string
  onSearchChange?: (value: string) => void
  avatarLabel?: string
  actions?: ReactNode
  onNavigate?: (path: string) => void
}) {
  return (
    <header className="topbar">
      {title ? <h1>{title}</h1> : null}

      {search ? (
        <div className="topbar-search">
          <IconSearch size={16} />
          <input
            type="search"
            value={searchValue ?? ''}
            onChange={(event) => onSearchChange?.(event.target.value)}
            placeholder={search}
            aria-label={search}
          />
        </div>
      ) : null}

      <div className="topbar-actions">
        {actions}
        <ThemeToggle />
        <NotificationBell onNavigate={onNavigate} />
        <span className="topbar-avatar" aria-hidden="true">
          {initials(avatarLabel || '')}
        </span>
      </div>
    </header>
  )
}

export default Topbar

