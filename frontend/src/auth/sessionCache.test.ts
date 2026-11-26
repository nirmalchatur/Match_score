import { afterEach, describe, expect, it, vi } from 'vitest'
import type { User } from '../lib/types'
import { clearSessionCache, readSessionCache, writeSessionCache } from './sessionCache'

const KEY = 'tailorup.session-cache'
const user = { id: 1, email: 'a@example.com' } as unknown as User

describe('sessionCache', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('round-trips a confirmed session', () => {
    writeSessionCache('authenticated', user)
    const cached = readSessionCache()
    expect(cached?.status).toBe('authenticated')
    expect(cached?.user).toEqual(user)
  })

  it('returns null when nothing is stored', () => {
    expect(readSessionCache()).toBeNull()
  })

  it('expires after 15 minutes so a revoked session cannot linger', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    writeSessionCache('authenticated', user)

    vi.setSystemTime(new Date('2026-01-01T00:14:59Z'))
    expect(readSessionCache()).not.toBeNull()

    vi.setSystemTime(new Date('2026-01-01T00:15:01Z'))
    expect(readSessionCache()).toBeNull()
  })

  it.each([
    ['corrupt JSON', '{not json'],
    ['missing cachedAt', JSON.stringify({ status: 'authenticated', user: null })],
    ['unknown status', JSON.stringify({ status: 'admin', user: null, cachedAt: Date.now() })],
    ['a bare string', JSON.stringify('authenticated')],
  ])('ignores %s rather than trusting it', (_label, raw) => {
    window.sessionStorage.setItem(KEY, raw)
    expect(readSessionCache()).toBeNull()
  })

  it('clears on sign-out', () => {
    writeSessionCache('authenticated', user)
    clearSessionCache()
    expect(readSessionCache()).toBeNull()
  })

  it('never throws when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })

    expect(() => writeSessionCache('anonymous', null)).not.toThrow()
    expect(readSessionCache()).toBeNull()
    expect(() => clearSessionCache()).not.toThrow()
  })
})
