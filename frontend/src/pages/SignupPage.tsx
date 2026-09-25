import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useAuth } from '../auth/useAuth'
import { AuthLayout } from './AuthLayout'
import { Alert } from '../components/primitives'
import { IconLogo } from '../components/Icons'

export function SignupPage() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (busy) return

    setBusy(true)
    setError('')
    try {
      await register(email.trim(), password, fullName.trim())
      // Brand-new accounts always go through master-resume onboarding.
      navigate('/setup/resume', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to create your account.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title="Create your workspace"
      subtitle="Start scoring job postings against your own resume."
      footer={
        <>
          Already have an account? <Link to="/login">Sign in</Link>
        </>
      }
    >
      <form className="auth-form" onSubmit={submit} noValidate>
        {error ? <Alert variant="danger">{error}</Alert> : null}

        <label className="form-label" htmlFor="full-name">
          Full name <span className="form-optional">optional</span>
        </label>
        <input
          id="full-name"
          className="auth-input"
          type="text"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          placeholder="Ada Lovelace"
          autoComplete="name"
          disabled={busy}
        />

        <label className="form-label" htmlFor="signup-email">
          Email
        </label>
        <input
          id="signup-email"
          className="auth-input"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
          required
          disabled={busy}
        />

        <label className="form-label" htmlFor="signup-password">
          Password
        </label>
        <input
          id="signup-password"
          className="auth-input"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="At least 8 characters"
          autoComplete="new-password"
          minLength={8}
          required
          disabled={busy}
        />

        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {busy ? <span className="spinner" /> : <IconLogo size={15} />}
          {busy ? 'Creating account…' : 'Create account'}
        </button>

        <p className="auth-terms">
          Your resume and job data stay private to your account.
        </p>
      </form>
    </AuthLayout>
  )
}

export default SignupPage
