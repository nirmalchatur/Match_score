import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './useAuth'
import { BrandLoader } from '../components/BrandLoader'

/** Full-screen spinner used while the session is being resolved. */
function Waiting() {
  return <BrandLoader label="Restoring your session" />
}

/** Gate for signed-out visitors: bounce an authenticated user to the workspace. */
export function RequireAnonymous() {
  const { status } = useAuth()

  if (status === 'loading') return <Waiting />

  if (status === 'authenticated') {
    return <Navigate to="/app/dashboard" replace />
  }

  return <Outlet />
}

/** Gate for private routes. Sends signed-out visitors to /login. */
export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <Waiting />

  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}

/**
 * Gate for the workspace. A signed-in account without a master resume is
 * sent to onboarding first, because scoring cannot run without one.
 */
export function RequireMasterResume() {
  const { status, user } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <Waiting />

  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (user && !user.has_master_resume) {
    return <Navigate to="/setup/resume" replace />
  }

  return <Outlet />
}
