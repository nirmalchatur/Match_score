import { createContext, useContext } from 'react'
import type { User } from '../lib/types'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export type AuthContextValue = {
  status: AuthStatus
  user: User | null
  login: (email: string, password: string) => Promise<User>
  register: (email: string, password: string, fullName?: string) => Promise<User>
  logout: () => Promise<void>
  /** Re-read the account, e.g. after a master resume upload. */
  refresh: () => Promise<void>
  markSessionExpired: () => void
}

/**
 * Shared auth context.
 *
 * Lives in its own module so this file exports no React component, which
 * keeps Fast Refresh working for the provider.
 */
export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside an AuthProvider')
  }
  return context
}
