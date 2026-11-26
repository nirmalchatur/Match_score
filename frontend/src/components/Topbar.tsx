import { useState } from 'react'
import type { FormEvent, ReactNode, Ref } from 'react'
import { initials } from '../lib/format'
import NotificationBell from './NotificationBell'
import { IconMenu, IconSearch } from './Icons'
import ThemeToggle from './ThemeToggle'

export function Topbar({
  title,
  search,
  onSearch,
  avatarLabel,
  actions,
  onNavigate,
  onMenu,
  menuOpen,
  menuButtonRef,
}: {
  title?: string
  /** Placeholder for the workspace search. Omit to hide the search box. */
  search?: string
  /** Called with the trimmed query when the search form is submitted. */
  onSearch?: (query: string) => void
  avatarLabel?: string
  actions?: ReactNode
  onNavigate?: (path: string) => void
  /** Opens the navigation drawer. The button only shows on narrow screens. */
  onMenu?: () => void
  menuOpen?: boolean
  menuButtonRef?: Ref<HTMLButtonElement>
}) {
  // Local, not lifted: the box is a launcher for the Jobs search, not a live
  // filter. It used to be a controlled input whose value nothing ever read,
  // so typing in it did nothing at all.
  const [query, setQuery] = useState('')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) return
    onSearch?.(trimmed)
    setQuery('')
  }

  return (
    <header className="topbar">
      {onMenu ? (
        <button
          ref={menuButtonRef}
          type="button"
          className="btn btn-ghost btn-icon topbar-menu"
          onClick={onMenu}
          aria-label="Open navigation"
          aria-expanded={menuOpen ?? false}
          aria-controls="app-sidebar"
        >
          <IconMenu size={18} />
        </button>
      ) : null}

      {title ? <h1>{title}</h1> : null}

      {search && onSearch ? (
        <form className="topbar-search" role="search" onSubmit={submit}>
          <IconSearch size={16} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={search}
            aria-label={search}
            enterKeyHint="search"
          />
        </form>
      ) : null}

      <div className="topbar-actions">
        {actions}
        <span className="topbar-theme">
          <ThemeToggle />
        </span>
        <NotificationBell onNavigate={onNavigate} />
        <span className="topbar-avatar" aria-hidden="true">
          {initials(avatarLabel || '')}
        </span>
      </div>
    </header>
  )
}

export default Topbar
