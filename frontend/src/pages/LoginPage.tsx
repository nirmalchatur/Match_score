import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useAuth } from '../auth/useAuth'
import { AuthLayout } from './AuthLayout'
import { Alert } from '../components/primitives'
import { IconLogo } from '../components/Icons'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const from = (location.state as { from?: string } | null)?.from

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (busy) return

    setBusy(true)
    setError('')
    try {
      const user = await login(email.trim(), password)
      // A user with no master resume must finish onboarding first.
      navigate(user.has_master_resume || from ? (from || '/app/dashboard') : '/setup/resume', {
        replace: true,
      })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to sign in. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to your TailorUp workspace."
      footer={
        <>
          New to TailorUp? <Link to="/signup">Create an account</Link>
        </>
      }
    >
      <form className="auth-form" onSubmit={submit} noValidate>
        {error ? <Alert variant="danger">{error}</Alert> : null}

        <label className="form-label" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          className="auth-input"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
          required
          disabled={busy}
        />

        <label className="form-label" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          className="auth-input"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••"
          autoComplete="current-password"
          required
          disabled={busy}
        />

        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {busy ? <span className="spinner" /> : <IconLogo size={15} />}
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </AuthLayout>
  )
}

export default LoginPage
