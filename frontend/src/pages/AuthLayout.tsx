import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { IconLogo } from '../components/Icons'

const PROOF = [
  {
    title: 'One master resume',
    body: 'Upload a PDF once. Every analysis scores against it.',
  },
  {
    title: 'Real job data',
    body: 'Greenhouse postings are collected and parsed, not pasted by hand.',
  },
  {
    title: 'Your workspace',
    body: 'Jobs, resumes, and scores stay private to your account.',
  },
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
          One resume.
          <br />
          Every job.
          <br />
          <span className="gradient-text">A smarter workflow.</span>
        </h2>

        <ul className="auth-proof">
          {PROOF.map((item) => (
            <li key={item.title}>
              <span className="auth-proof-dot" />
              <div>
                <strong>{item.title}</strong>
                <p>{item.body}</p>
              </div>
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
