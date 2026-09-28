import { Link } from 'react-router-dom'
import { useEffect } from 'react'
import { applySeo } from '../lib/seo'
import { BrandMark, IconArrowRight, IconCheck } from '../components/Icons'

/**
 * Shown once, after an account is created.
 *
 * Sits between signup and onboarding so the account is acknowledged before the
 * user is dropped into a four-step form. It is deliberately not a dead end:
 * there is one obvious next action, and the rest of the flow is reachable
 * later from the dashboard.
 *
 * `noindex` — a "thanks" page is per-visit, not a destination anyone searches
 * for, and it has no content of its own.
 */
export function ThanksPage() {
  useEffect(() => {
    applySeo({
      title: 'Account created',
      description: 'Your TailorUp account is ready.',
      path: '/thanks',
      noindex: true,
    })
  }, [])

  return (
    <div className="mk-landing-shell">
      <div className="notfound thanks">
        <BrandMark size={40} className="notfound-mark" />
        <h1 className="notfound-title">Your account is ready</h1>
        <p className="notfound-body">
          Next: upload your master resume. It stays the single source of truth —
          tailoring creates new versions beside it and never edits it.
        </p>

        <ul className="thanks-list">
          <li>
            <IconCheck size={15} />
            Upload one master resume
          </li>
          <li>
            <IconCheck size={15} />
            Analyse a real job posting
          </li>
          <li>
            <IconCheck size={15} />
            See your match score and skill gap
          </li>
        </ul>

        <div className="notfound-actions">
          <Link to="/setup/resume" className="btn btn-primary btn-lg">
            Upload my resume
            <IconArrowRight size={16} />
          </Link>
          <Link to="/app/dashboard" className="btn btn-ghost btn-lg">
            Skip for now
          </Link>
        </div>
      </div>
    </div>
  )
}

export default ThanksPage
