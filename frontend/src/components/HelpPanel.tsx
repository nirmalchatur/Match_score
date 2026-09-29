import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { IconClose, IconHelp } from './Icons'

/**
 * In-app documentation.
 *
 * This replaced a link to `/docs/README.md`, which was dead: the frontend is a
 * static Vite bundle and serves nothing under `/docs`, so the browser asked the
 * app host for a Markdown file that was never there and got a 404. The Markdown
 * does exist, but in the repository, not in the deployment.
 *
 * So the reference material lives here, in the place the reader already is.
 * That has a cost worth naming: a second copy of the documentation can drift
 * from `docs/`. This one is deliberately scoped to the questions a person has
 * *while using the app* -- what this button does, what these commands mean,
 * why tailoring takes six minutes -- rather than reproducing the architecture
 * and deployment guides, which stay in the repo and are linked at the bottom.
 *
 * Everything here is written from behaviour that exists in this codebase.
 */

type Section = {
  id: string
  title: string
  body: React.ReactNode
}

const TERMINAL: [string, string][] = [
  ['help', 'This list. Every command is also in the sidebar console.'],
  ['status', 'Provider, model, availability, and whether a key is stored.'],
  ['jobs', 'Recent jobs with their match scores.'],
  ['sources', 'The ATS boards currently in the registry.'],
  ['quality [n]', 'Your saved qualities, or the catalogue for group n.'],
  ['env', 'Frontend build configuration.'],
  ['clear', 'Clear the buffer.'],
]

const LIMITS: [string, string][] = [
  ['Login', '5 / minute per IP'],
  ['Signup', '5 / hour per IP'],
  ['Anonymous API', '30 / minute per IP'],
  ['Signed-in API', '60 / minute per user'],
  ['AI tailoring', '5 / minute and 20 / hour per user'],
  ['DOCX / PDF', '10 / minute per user'],
]

const SECTIONS: Section[] = [
  {
    id: 'start',
    title: 'Getting started',
    body: (
      <>
        <p>
          TailorUp works in one direction: a job goes in, a scored resume comes
          out. The order matters, because each step needs the one before it.
        </p>
        <ol className="help-steps">
          <li>
            <strong>Upload a master resume.</strong> This is your single source of
            truth. Tailoring never modifies it; it produces a new version beside it.
          </li>
          <li>
            <strong>Analyze a job.</strong> Paste a posting URL. TailorUp pulls the
            description, extracts the requirements, and scores your master resume
            against them.
          </li>
          <li>
            <strong>Read the skill gap.</strong> Matched and missing skills, with
            the evidence for each match taken from your own resume.
          </li>
          <li>
            <strong>Tailor.</strong> AI rewrites your resume for that posting, and
            shows you a before/after you can accept or reject.
          </li>
          <li>
            <strong>Track the application.</strong> Move it through Saved, Applied,
            Screening, Interview, Offer, Rejected, Withdrawn.
          </li>
        </ol>
      </>
    ),
  },
  {
    id: 'terminal',
    title: 'The Dev console',
    body: (
      <>
        <p>
          The console in the sidebar is a real read-only diagnostic, not a
          decorative shell. Every command is answered from data the app already
          has. Nothing typed into it changes stored data.
        </p>
        <p>Type <code>help</code> to list them:</p>
        <dl className="help-terms">
          {TERMINAL.map(([cmd, desc]) => (
            <div className="help-term" key={cmd}>
              <dt><code>{cmd}</code></dt>
              <dd>{desc}</dd>
            </div>
          ))}
        </dl>
        <p className="help-note">
          Use <code>status</code> first when something is not working. It reports
          which provider is active and whether a key is stored, which resolves
          most tailoring problems in one step.
        </p>
      </>
    ),
  },
  {
    id: 'tailoring',
    title: 'Why tailoring is slow',
    body: (
      <>
        <p>
          Tailoring is a real model call, and on a CPU-only machine it is{' '}
          <strong>slow</strong>. A <code>llama3.1</code> request has been measured
          at roughly <strong>364 seconds</strong> &mdash; about six minutes. That is
          the expected behaviour on that hardware, not a hang and not a bug.
        </p>
        <p>
          If you are configuring Ollama yourself, <code>OLLAMA_TIMEOUT</code> must
          exceed 180 seconds, or the request is abandoned before the model
          finishes and you see a timeout instead of a result.
        </p>
        <h4>Tailoring fails or never finishes</h4>
        <ul>
          <li>
            <strong>No provider configured.</strong> <code>status</code> reports{' '}
            <code>(none configured)</code>. Set one in Settings, or set{' '}
            <code>AI_PROVIDER</code> in the environment.
          </li>
          <li>
            <strong>Ollama not running.</strong> Check the model is pulled with{' '}
            <code>ollama list</code>. A missing model fails at the first request,
            not at startup.
          </li>
          <li>
            <strong>Output rejected.</strong> If the model invented experience the
            request is refused rather than returned. The violations are shown to
            you &mdash; that is the factual validator working, not a failure.
          </li>
          <li>
            <strong>Throttled.</strong> 5 per minute and 20 per hour. A 429 with{' '}
            <code>code: rate_limited</code> means you hit the ceiling; wait for the
            window to pass.
          </li>
        </ul>
      </>
    ),
  },
  {
    id: 'limits',
    title: 'Rate limits',
    body: (
      <>
        <p>Defaults, all overridable through <code>TAILORUP_RATE_LIMIT_*</code>:</p>
        <dl className="help-terms">
          {LIMITS.map(([what, limit]) => (
            <div className="help-term" key={what}>
              <dt>{what}</dt>
              <dd>{limit}</dd>
            </div>
          ))}
        </dl>
        <p className="help-note">
          A 429 returns <code>Retry-After</code>. It says nothing about your data
          &mdash; a throttled request is refused on quota alone, and one account
          can never see another account&apos;s resumes or jobs.
        </p>
      </>
    ),
  },
  {
    id: 'privacy',
    title: 'Privacy and keys',
    body: (
      <>
        <p>
          Your resume does not have to leave your machine. The default provider is
          Ollama, running locally, and your resume is never shipped to a
          third-party API just to be scored.
        </p>
        <p>
          If you use a hosted provider, your key is entered in your browser,
          encrypted at rest with Fernet, and never returned by the API. Signing
          out removes it from the server.
        </p>
        <p className="help-note">
          Full detail, including the request-ordering reasoning, is in{' '}
          <code>docs/SECURITY.md</code> in the repository.
        </p>
      </>
    ),
  },
]

export function HelpPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [active, setActive] = useState(SECTIONS[0].id)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    // The app stays mounted behind the scrim, so lock page scroll while help is
    // open. Without this the background scrolls under a fixed panel.
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [open, onClose])

  if (!open) return null

  const section = SECTIONS.find((s) => s.id === active) ?? SECTIONS[0]

  return createPortal(
    <div
      className="help-scrim"
      role="dialog"
      aria-modal="true"
      aria-labelledby="help-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="help-panel">
        {/*
         * The header is a file tab rather than a plain title bar, because that
         * is the mental model the panel is now serving: this is a document the
         * user is reading, not a settings dialog they are dismissing. The
         * "Preview" affordance on the right is a live region label, not a
         * button, so it cannot be clicked into a state that does nothing --
         * the content is already the rendered preview.
         */}
        <header className="help-head">
          <span className="help-title-wrap">
            <IconHelp size={17} />
            <h2 className="help-title" id="help-title">
              <span className="help-file">HELP.md</span>
            </h2>
          </span>

          <div className="help-head-actions">
            <span className="help-preview-tag">Preview</span>
            <button
              type="button"
              className="btn btn-ghost btn-icon"
              onClick={onClose}
              aria-label="Close help"
            >
              <IconClose size={16} />
            </button>
          </div>
        </header>

        <div className="help-body">
          <nav className="help-nav" aria-label="Help sections">
            {SECTIONS.map((s, index) => (
              <button
                key={s.id}
                type="button"
                className={`help-tab${s.id === active ? ' active' : ''}`}
                onClick={() => setActive(s.id)}
                aria-current={s.id === active ? 'true' : undefined}
              >
                {/* The number is part of the label rather than a pseudo-element
                    so it is announced with the tab name. */}
                <span className="help-tab-num">
                  {String(index + 1).padStart(2, '0')}
                </span>
                {s.title}
              </button>
            ))}
          </nav>

          <div className="help-content" role="region" aria-label={section.title}>
            <h3 className="help-heading">
              <span className="help-heading-num">
                {String(SECTIONS.findIndex((s) => s.id === active) + 1).padStart(2, '0')}
              </span>
              {section.title}
            </h3>
            {section.body}
          </div>
        </div>

        <footer className="help-foot">
          <span>Architecture, deployment and API detail live in the repository:</span>
          <a
            href="https://github.com/nirmalchatur/Match_score/tree/main/docs"
            target="_blank"
            rel="noreferrer"
          >
            docs/ on GitHub
          </a>
        </footer>
      </div>
    </div>,
    document.body,
  )
}

export default HelpPanel
