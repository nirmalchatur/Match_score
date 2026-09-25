import type { JobStatus, StepStatus } from './types'

/** Round a 0-100 match score for display. */
export function formatScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return '—'
  const rounded = Math.round(score)
  return `${rounded}%`
}

export type Tone = 'success' | 'warning' | 'danger' | 'accent' | 'info' | 'neutral'

/** Map a match score onto a semantic tone. */
export function scoreTone(score: number | null | undefined): Tone {
  if (score == null || Number.isNaN(score)) return 'neutral'
  if (score >= 80) return 'success'
  if (score >= 60) return 'warning'
  if (score >= 40) return 'danger'
  return 'neutral'
}

/** CSS colour for a score, used by the progress ring and inline values. */
export function scoreColor(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return 'var(--text-dim)'
  if (score >= 80) return 'var(--success)'
  if (score >= 60) return 'var(--warning)'
  if (score >= 40) return 'var(--danger)'
  return 'var(--text-dim)'
}

const STATUS_TONE: Record<JobStatus, Tone> = {
  PENDING: 'neutral',
  NEW: 'neutral',
  RUNNING: 'warning',
  PROCESSING: 'warning',
  COMPLETED: 'success',
  READY: 'success',
  SKIPPED: 'neutral',
  FAILED: 'danger',
}

export function statusTone(status: string | undefined): Tone {
  return STATUS_TONE[(status || 'PENDING').toUpperCase() as JobStatus] ?? 'neutral'
}

export function statusLabel(status: string | undefined): string {
  const value = (status || 'PENDING').toUpperCase()
  return value.charAt(0) + value.slice(1).toLowerCase()
}

export function stepIcon(status: StepStatus): 'check' | 'spinner' | 'pending' {
  const value = String(status).toLowerCase()
  if (value === 'complete' || value === 'completed' || value === 'done') return 'check'
  if (value === 'running' || value === 'active') return 'spinner'
  return 'pending'
}

const UNITS: Array<[number, Intl.RelativeTimeFormatUnit]> = [
  [60, 'second'],
  [3600, 'minute'],
  [86400, 'hour'],
  [604800, 'day'],
  [2629800, 'week'],
  [31557600, 'month'],
]

/** "3h ago" style relative time. */
export function formatRelative(iso: string | undefined): string {
  if (!iso) return ''
  const timestamp = Date.parse(iso)
  if (Number.isNaN(timestamp)) return ''

  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  const seconds = (timestamp - Date.now()) / 1000
  const magnitude = Math.abs(seconds)

  if (magnitude < 60) return formatter.format(Math.round(seconds), 'second')

  for (const [limit, unit] of UNITS) {
    if (magnitude < limit * 60) {
      return formatter.format(Math.round(seconds / limit), unit)
    }
  }

  return formatter.format(Math.round(seconds / 31557600), 'year')
}

export function formatDate(iso: string | undefined): string {
  if (!iso) return ''
  const timestamp = Date.parse(iso)
  if (Number.isNaN(timestamp)) return ''
  return new Intl.DateTimeFormat('en', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(timestamp))
}

/** Up to two uppercase initials, for the company avatar. */
export function initials(value: string): string {
  const words = (value || '?')
    .split(/[\s\-_]+/)
    .filter(Boolean)

  if (words.length === 0) return '?'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()

  return (words[0][0] + words[1][0]).toUpperCase()
}

/** Hostname without protocol/www, for showing where a job came from. */
export function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}
