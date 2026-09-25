import type { ReactNode } from 'react'

export function Topbar({
  eyebrow,
  title,
  actions,
}: {
  eyebrow: string
  title: string
  actions?: ReactNode
}) {
  return (
    <header className="topbar">
      <div className="topbar-copy">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      {actions ? <div className="topbar-actions">{actions}</div> : null}
    </header>
  )
}
