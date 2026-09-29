import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, api } from '../lib/api'
import type { User } from '../lib/types'
import { AuthContext } from './useAuth'
import type { AuthStatus } from './useAuth'
import { clearSessionCache, readSessionCache, writeSessionCache } from './sessionCache'

/**
 * How long to wait for `/api/auth/me/` before giving up and treating the
 * session as unknown.
 *
 * The endpoint is a single indexed read and normally answers in tens of
 * milliseconds. But a free-tier host that has spun down to zero instances can
 * take 30-60s to wake, and without a bound the app sits on a spinner for the
 * whole of that with no way out and nothing to tell the user. 12s is well past
 * a healthy response and well short of an outage, so the worst case is a
 * sign-in prompt rather than a frozen tab.
 */
const ME_TIMEOUT_MS = 12_000

/**
 * Session bootstrap.
 *
 * Auth state comes from the backend, not from client storage: the session
 * cookie is HttpOnly, so `/api/auth/me/` is the only authority on whether
 * anyone is signed in.
 *
 * What changed, and why it matters
 * -------------------------------
 * This used to start at `status: 'loading'` and every route guard rendered a
 * full-screen "Restoring your session" spinner until `/api/auth/me/` came
 * back. The public landing page paid that cost too, for a question it does not
 * even need answered -- so a cold backend turned the marketing page into a
 * blank screen for the best part of a minute.
 *
 * Now the provider seeds itself from `sessionCache` (a short-lived
 * sessionStorage hint) and reconciles with the server in the background. The
 * common case -- a returning visitor refreshing the page -- paints the real UI
 * immediately and silently corrects itself if the cache was wrong. A first-time
 * visitor with no cache still shows a brief loader, but that loader is now
 * bounded by ME_TIMEOUT_MS instead of by however long the host takes to wake.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  // Seeded synchronously during the first render, so a returning user never
  // sees a loading frame at all. `?? 'loading'` keeps the type honest when the
  // cache is absent rather than widening it to include undefined.
  const cached = useMemo(() => readSessionCache(), [])
  const [status, setStatus] = useState<AuthStatus>(cached?.status ?? 'loading')
  const [user, setUser] = useState<User | null>(cached?.user ?? null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const data = await api.me(ME_TIMEOUT_MS)
        if (cancelled) return
        setUser(data.user)
        setStatus(data.authenticated ? 'authenticated' : 'anonymous')
        // Only a server answer is worth caching. Writing the seeded value back
        // would refresh its age on every load and let a stale "authenticated"
        // live forever.
        writeSessionCache(data.authenticated ? 'authenticated' : 'anonymous', data.user)
      } catch {
        if (cancelled) return
        setUser(null)
        setStatus('anonymous')
        clearSessionCache()
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.login(email, password)
    setUser(data.user)
    setStatus('authenticated')
    writeSessionCache('authenticated', data.user)
    return data.user
  }, [])

  const register = useCallback(async (email: string, password: string, fullName?: string) => {
    const data = await api.register(email, password, fullName)
    setUser(data.user)
    setStatus('authenticated')
    writeSessionCache('authenticated', data.user)
    return data.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch (error) {
      // A failed logout call should still clear local state.
      if (!(error instanceof ApiError)) throw error
    }
    setUser(null)
    setStatus('anonymous')
    clearSessionCache()
  }, [])

  const refresh = useCallback(async () => {
    try {
      const data = await api.me()
      setUser(data.user)
      setStatus(data.authenticated ? 'authenticated' : 'anonymous')
      writeSessionCache(data.authenticated ? 'authenticated' : 'anonymous', data.user)
    } catch {
      setUser(null)
      setStatus('anonymous')
      clearSessionCache()
    }
  }, [])

  const markSessionExpired = useCallback(() => {
    setUser(null)
    setStatus('anonymous')
    clearSessionCache()
  }, [])

  const value = useMemo(
    () => ({ status, user, login, register, logout, refresh, markSessionExpired }),
    [status, user, login, register, logout, refresh, markSessionExpired],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export default AuthProvider
