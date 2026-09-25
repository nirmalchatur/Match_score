import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { IconLogo } from '../components/Icons'

const PROOF = [
  'Job postings collected and parsed',
  'Scored against your master resume',
  'Every analysis saved to your workspace',
]

/** Split layout shared by sign-in and sign-up. */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <div className="auth-shell">
      <div className="bg-fx" aria-hidden="true" />

      <aside className="auth-aside">
        <Link to="/" className="auth-brand">
          <span className="brand-mark">
            <IconLogo size={19} />
          </span>
          <span className="brand-name">TailorUp</span>
        </Link>

        <h2 className="auth-pitch">
          Build applications
          <br />
          around the job <span className="gradient-text">not the other way around.</span>
        </h2>

        <p className="auth-sub">
          Your career workspace is waiting. Sign in to keep analysing, matching, and improving.
        </p>

        <ul className="auth-proof">
          <div className="auth-proof-label">What you get</div>
          {PROOF.map((item) => (
            <li key={item}>
              <span className="auth-proof-dot" />
              {item}
            </li>
          ))}
        </ul>
      </aside>

      <main className="auth-main">
        <div className="auth-card">
          <Link to="/" className="auth-mobile-brand">
            <span className="brand-mark">
              <IconLogo size={17} />
            </span>
            <span className="brand-name">TailorUp</span>
          </Link>

          <h1 className="auth-title">{title}</h1>
          <p className="auth-sub">{subtitle}</p>

          {children}

          <div className="auth-footer">{footer}</div>
        </div>
      </main>
    </div>
  )
}

export default AuthLayout
