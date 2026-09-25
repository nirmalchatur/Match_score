import type { CSSProperties, ReactNode } from 'react'
import type { Tone } from '../lib/format'
import { formatScore, scoreColor } from '../lib/format'
import { IconAlert, IconInbox } from './Icons'

/* ---------- Pill ---------- */
export function Pill({
  tone = 'neutral',
  live = false,
  children,
}: {
  tone?: Tone
  live?: boolean
  children: ReactNode
}) {
  return (
    <span className={`pill pill-${tone}${live ? ' pill-running' : ''}`}>{children}</span>
  )
}

/* ---------- Score ring ---------- */
export function ScoreRing({ score, size = 46 }: { score: number | null; size?: number }) {
  const stroke = size < 40 ? 3.5 : 4
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const pct = score == null ? 0 : Math.max(0, Math.min(100, score)) / 100
  const offset = circumference * (1 - pct)

  const ringStyle = {
    '--ring-circ': `${circumference}`,
    '--ring-offset': `${offset}`,
  } as CSSProperties

  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} role="img" aria-label={`Match score ${formatScore(score)}`}>
        <circle className="ring-track" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} />
        <circle
          className="ring-fill"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          stroke={scoreColor(score)}
          strokeDasharray={circumference}
          style={ringStyle}
        />
      </svg>
      <span className="ring-label mono" style={{ color: scoreColor(score) }}>
        {score == null ? '—' : Math.round(score)}
      </span>
    </div>
  )
}

/* ---------- Stat card ---------- */
export function StatCard({
  label,
  value,
  unit,
  hint,
  icon,
  tone,
}: {
  label: string
  value: ReactNode
  unit?: string
  hint?: string
  icon?: ReactNode
  tone?: 'green' | 'blue' | 'amber'
}) {
  return (
    <div className="stat">
      {icon ? <span className={`stat-icon${tone ? ` ${tone}` : ''}`}>{icon}</span> : null}
      <div className="stat-top">
        <span className="stat-label">{label}</span>
      </div>
      <div className="stat-value">
        {value}
        {unit ? <span className="unit">{unit}</span> : null}
      </div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </div>
  )
}

/* ---------- Empty state ---------- */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <IconInbox size={22} />
      </span>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action ? <div style={{ marginTop: 10 }}>{action}</div> : null}
    </div>
  )
}

/* ---------- Skeleton ---------- */
export function Skeleton({
  width = '100%',
  height = 14,
  radius = 6,
}: {
  width?: number | string
  height?: number | string
  radius?: number
}) {
  return <div className="skeleton" style={{ width, height, borderRadius: radius }} />
}

export function JobRowSkeleton() {
  return (
    <div className="sk-row">
      <Skeleton width={36} height={36} radius={10} />
      <div style={{ flex: 1, display: 'grid', gap: 7 }}>
        <Skeleton width="55%" />
        <Skeleton width="35%" height={11} />
      </div>
      <Skeleton width={46} height={46} radius={23} />
    </div>
  )
}

/* ---------- Alert ---------- */
export function Alert({
  variant = 'info',
  children,
  onDismiss,
}: {
  variant?: 'info' | 'danger' | 'warning' | 'success'
  children: ReactNode
  onDismiss?: () => void
}) {
  return (
    <div className={`alert alert-${variant}`} role={variant === 'danger' ? 'alert' : 'status'}>
      <IconAlert size={17} />
      <div className="alert-body">{children}</div>
      {onDismiss ? (
        <button type="button" onClick={onDismiss} aria-label="Dismiss">
          ✕
        </button>
      ) : null}
    </div>
  )
}
