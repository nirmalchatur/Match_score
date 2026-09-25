import type { ReactNode } from 'react'
import { initials } from '../lib/format'
import { IconBell, IconSearch } from './Icons'

export function Topbar({
  title,
  search,
  searchValue,
  onSearchChange,
  avatarLabel,
  actions,
}: {
  title?: string
  search?: string
  searchValue?: string
  onSearchChange?: (value: string) => void
  avatarLabel?: string
  actions?: ReactNode
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
        <span className="bell" role="img" aria-label="Notifications">
          <IconBell size={18} />
        </span>
        <span className="topbar-avatar" aria-hidden="true">
          {initials(avatarLabel || '')}
        </span>
      </div>
    </header>
  )
}

export default Topbar

