import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, api } from '../lib/api'
import type { User } from '../lib/types'
import { AuthContext } from './useAuth'
import type { AuthStatus } from './useAuth'

/**
 * Session bootstrap.
 *
 * Auth state comes from the backend, not from client storage: the session
 * cookie is HttpOnly, so /api/auth/me/ is the only source of truth.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const data = await api.me()
        if (cancelled) return
        setUser(data.user)
        setStatus(data.authenticated ? 'authenticated' : 'anonymous')
      } catch {
        if (cancelled) return
        setUser(null)
        setStatus('anonymous')
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
    return data.user
  }, [])

  const register = useCallback(async (email: string, password: string, fullName?: string) => {
    const data = await api.register(email, password, fullName)
    setUser(data.user)
    setStatus('authenticated')
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
  }, [])

  const refresh = useCallback(async () => {
    try {
      const data = await api.me()
      setUser(data.user)
      setStatus(data.authenticated ? 'authenticated' : 'anonymous')
    } catch {
      setUser(null)
      setStatus('anonymous')
    }
  }, [])

  const markSessionExpired = useCallback(() => {
    setUser(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo(
    () => ({ status, user, login, register, logout, refresh, markSessionExpired }),
    [status, user, login, register, logout, refresh, markSessionExpired],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export default AuthProvider
