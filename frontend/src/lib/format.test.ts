import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  atsLabel,
  formatDate,
  formatRelative,
  formatScore,
  initials,
  scoreColor,
  scoreTone,
  sourceHost,
  statusLabel,
  statusTone,
  stepIcon,
} from './format'

describe('formatScore', () => {
  it('rounds to a whole percent', () => {
    expect(formatScore(72.4)).toBe('72%')
    expect(formatScore(72.5)).toBe('73%')
    expect(formatScore(0)).toBe('0%')
  })

  it('shows a dash for a missing score instead of "NaN%"', () => {
    expect(formatScore(null)).toBe('—')
    expect(formatScore(undefined)).toBe('—')
    expect(formatScore(Number.NaN)).toBe('—')
  })
})

describe('scoreTone / scoreColor', () => {
  // The two functions must agree on band edges, or the ring colour and the
  // chip colour for the same job disagree.
  it.each([
    [100, 'success', 'var(--success)'],
    [80, 'success', 'var(--success)'],
    [79.9, 'warning', 'var(--warning)'],
    [60, 'warning', 'var(--warning)'],
    [59.9, 'danger', 'var(--danger)'],
    [40, 'danger', 'var(--danger)'],
    [39.9, 'neutral', 'var(--text-dim)'],
    [null, 'neutral', 'var(--text-dim)'],
  ])('%s -> %s', (score, tone, color) => {
    expect(scoreTone(score)).toBe(tone)
    expect(scoreColor(score)).toBe(color)
  })
})

describe('statusTone / statusLabel', () => {
  it('is case-insensitive and defaults to pending', () => {
    expect(statusTone('completed')).toBe('success')
    expect(statusTone('FAILED')).toBe('danger')
    expect(statusTone(undefined)).toBe('neutral')
    expect(statusLabel(undefined)).toBe('Pending')
    expect(statusLabel('running')).toBe('Running')
  })

  it('treats an unknown status as neutral rather than crashing', () => {
    expect(statusTone('SOMETHING_NEW')).toBe('neutral')
  })
})

describe('stepIcon', () => {
  it.each([
    ['complete', 'check'],
    ['DONE', 'check'],
    ['active', 'spinner'],
    ['running', 'spinner'],
    ['queued', 'pending'],
  ])('%s -> %s', (status, icon) => {
    expect(stepIcon(status as never)).toBe(icon)
  })
})

describe('formatRelative', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-15T12:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns an empty string for missing or unparseable input', () => {
    expect(formatRelative(undefined)).toBe('')
    expect(formatRelative('not a date')).toBe('')
  })

  // Regression: the unit table was offset by one, so each of these came out
  // one unit too small ("3 hours ago" read "3 minutes ago").
  it.each([
    ['2026-06-15T11:59:30Z', '30 seconds ago'],
    ['2026-06-15T11:58:00Z', '2 minutes ago'],
    ['2026-06-15T09:00:00Z', '3 hours ago'],
    ['2026-06-14T12:00:00Z', 'yesterday'],
    ['2026-06-12T12:00:00Z', '3 days ago'],
    ['2026-06-01T12:00:00Z', '2 weeks ago'],
    ['2026-03-15T12:00:00Z', '3 months ago'],
    ['2024-06-15T12:00:00Z', '2 years ago'],
    ['2026-06-15T14:00:00Z', 'in 2 hours'],
  ])('%s -> %s', (iso, expected) => {
    expect(formatRelative(iso)).toBe(expected)
  })
})

describe('formatDate', () => {
  it('formats an ISO timestamp and ignores garbage', () => {
    expect(formatDate('2026-03-09T10:00:00Z')).toBe('Mar 9, 2026')
    expect(formatDate('nope')).toBe('')
    expect(formatDate(undefined)).toBe('')
  })
})

describe('initials', () => {
  it('uses the first letters of the first two words', () => {
    expect(initials('Acme Corp')).toBe('AC')
    expect(initials('open-ai labs')).toBe('OA')
  })

  it('uses two letters of a single word, and survives empty input', () => {
    expect(initials('stripe')).toBe('ST')
    expect(initials('')).toBe('?')
    expect(initials('   ')).toBe('?')
  })
})

describe('sourceHost', () => {
  it('strips the protocol and www', () => {
    expect(sourceHost('https://www.boards.greenhouse.io/acme/jobs/1')).toBe('boards.greenhouse.io')
  })

  it('returns an empty string for something that is not a URL', () => {
    expect(sourceHost('boards.greenhouse.io')).toBe('')
  })
})

describe('atsLabel', () => {
  it('maps known slugs regardless of case and whitespace', () => {
    expect(atsLabel(' Greenhouse ')).toBe('Greenhouse')
    expect(atsLabel('linkedin')).toBe('LinkedIn')
  })

  it('falls back to the slug, then to a generic label', () => {
    expect(atsLabel('smartrecruiters')).toBe('smartrecruiters')
    expect(atsLabel(null)).toBe('Other board')
    expect(atsLabel('')).toBe('Other board')
  })
})
