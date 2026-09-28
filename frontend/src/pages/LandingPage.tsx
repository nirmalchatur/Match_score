import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { useReveal } from '../hooks/useReveal'
import {
  IconArrowRight,
  IconBriefcase,
  IconCheck,
  IconFile,
  IconGitHub,
  IconLogo,
  IconRadar,
  IconSearch,
  IconTarget,
  IconTrend,
} from '../components/Icons'

const GITHUB_URL = 'https://github.com/nirmalchatur/Match_score'

/* ---------- Workflow ---------- */

const STEPS = [
  {
    n: '01',
    title: 'Set your master resume',
    body: 'Upload one resume you are happy with. TailorUp treats it as the baseline it measures every other role against.',
  },
  {
    n: '02',
    title: 'Add a job posting',
    body: 'Paste a link to the role. TailorUp fetches the posting and reads the parts that actually decide the fit.',
  },
  {
    n: '03',
    title: 'Extract the role',
    body: 'Requirements, responsibilities, skills, experience and education are pulled out into structured, reviewable fields.',
  },
  {
    n: '04',
    title: 'Score your match',
    body: 'Your master resume is compared against the role to produce a match score and an explicit list of what is missing.',
  },
  {
    n: '05',
    title: 'Tailor and apply',
    body: 'Work from the gap list to decide what to emphasise and what to leave out before you send.',
    soon: true,
  },
]

/* ---------- Capabilities ---------- */

const FEATURES = [
  {
    Icon: IconSearch,
    title: 'Job analysis',
    body: 'Turns a wall of posting text into structured requirements, responsibilities, skills, experience and education.',
  },
  {
    Icon: IconRadar,
    title: 'Resume matching',
    body: 'Compares your master resume against a role and reports alignment across every dimension that was extracted.',
  },
  {
    Icon: IconTarget,
    title: 'Skill gap analysis',
    body: 'Pinpoints the exact skills a role asks for that your resume does not yet evidence.',
  },
  {
    Icon: IconTrend,
    title: 'Match score',
    body: 'One precise percentage summarising how well the role fits, so you can triage applications instead of guessing.',
  },
  {
    Icon: IconBriefcase,
    title: 'Job workspace',
    body: 'Every role you have analysed stays organised in one place, with its score and analysis attached.',
  },
  {
    Icon: IconFile,
    title: 'Application tracker',
    body: 'Follow each application through to offer rather than keeping it all in your head.',
    soon: true,
  },
]

/* ---------- Hero: an illustrative analysis result ---------- */

const MATCH_REPORT = {
  role: 'Senior Backend Engineer',
  company: 'Nimbus Systems',
  score: 82,
  verdict: 'Strong match',
  breakdown: [
    { label: 'Skills', pct: 92 },
    { label: 'Experience', pct: 84 },
    { label: 'Responsibilities', pct: 76 },
    { label: 'Education', pct: 70 },
  ],
  matched: ['Python', 'Django', 'PostgreSQL', 'Docker', 'AWS'],
  missing: 'Kubernetes',
}

/* Runs on your own machine; the provider is configurable. */
const LOCAL_CONFIG = [
  { key: 'AI_PROVIDER', value: 'ollama' },
  { key: 'OLLAMA_BASE_URL', value: 'http://localhost:11434' },
  { key: 'OLLAMA_MODEL', value: 'llama3.1' },
]

/** One shared section header, so the vertical rhythm never drifts. */
function SectionHead({ eyebrow, title, lede }: { eyebrow: string; title: string; lede?: string }) {
  return (
    <header className="mk-head">
      <p className="mk-eyebrow">{eyebrow}</p>
      <h2 className="mk-heading">{title}</h2>
      {lede ? <p className="mk-lede">{lede}</p> : null}
    </header>
  )
}

/**
 * Stagger helper for scroll reveals.
 *
 * `transition-delay` cannot be set from a plain object without a cast,
 * because React's `CSSProperties` only knows about real CSS properties,
 * not custom ones. Doing the cast once here keeps the call sites readable.
 */
const delay = (ms: number) => ({ '--reveal-delay': `${ms}ms` }) as CSSProperties

export function LandingPage() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'
  const primaryTo = signedIn ? '/app/dashboard' : '/signup'

  // Scroll reveals. Renders nothing and adds no markup, so the page still
  // reads correctly if the observer never runs.
  useReveal()

  return (
    <div className="landing mk-animate">
      <div className="mk-bg" aria-hidden="true" />

      <header className="mk-nav">
        <div className="mk-nav-inner">
          <Link to="/" className="brand">
            <span className="brand-mark">
              <IconLogo size={18} />
            </span>
            <span className="brand-name">TailorUp</span>
          </Link>

          <nav className="mk-links" aria-label="Sections">
            <a href="#capabilities">Product</a>
            <a href="#workflow">How it works</a>
            <a href="#privacy">Privacy</a>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">
              GitHub
            </a>
          </nav>

          <div className="mk-nav-actions">
            <Link to={signedIn ? '/app/dashboard' : '/login'} className="mk-link-btn">
              {signedIn ? 'Dashboard' : 'Log in'}
            </Link>
            <Link to={primaryTo} className="btn btn-primary">
              {signedIn ? 'Open dashboard' : 'Get started'}
              <IconArrowRight size={15} />
            </Link>
          </div>
        </div>
      </header>

      <main>
        {/* ---------- Hero ---------- */}
        <section className="mk-hero">
          <div className="mk-hero-copy">
            <p className="mk-eyebrow">
              <span className="mk-eyebrow-dot" />
              Open-source job analysis
            </p>

            <h1 className="mk-title">
              Know how well you fit <span className="mk-title-em">before</span> you apply.
            </h1>

            <p className="mk-lede">
              TailorUp reads a job posting, pulls out what it is actually asking for, and scores
              your master resume against it &mdash; instead of guessing which version to send.
            </p>

            <div className="mk-actions">
              <Link to={primaryTo} className="btn btn-primary btn-lg">
                {signedIn ? 'Open dashboard' : 'Analyse your first job'}
                <IconArrowRight size={16} />
              </Link>
              <a className="btn btn-ghost btn-lg" href="#workflow">
                See how it works
              </a>
            </div>

            <ul className="mk-points">
              <li>
                <IconCheck size={15} />
                Runs locally with Ollama
              </li>
              <li>
                <IconCheck size={15} />
                Free and open source
              </li>
              <li>
                <IconCheck size={15} />
                No credit card
              </li>
            </ul>
          </div>

          {/* An illustrative match report, not a live screenshot. */}
          <div className="mk-report">
            <div className="mk-report-head">
              <div>
                <p className="mk-report-role">{MATCH_REPORT.role}</p>
                <p className="mk-report-co">{MATCH_REPORT.company}</p>
              </div>
              <div className="mk-report-score">
                <span className="mk-report-score-value">{MATCH_REPORT.score}%</span>
                <span className="mk-report-score-label">{MATCH_REPORT.verdict}</span>
              </div>
            </div>

            <div className="mk-bars">
              {MATCH_REPORT.breakdown.map((row) => (
                <div className="mk-bar" key={row.label}>
                  <span className="mk-bar-label">{row.label}</span>
                  <span className="mk-bar-track">
                    <span className="mk-bar-fill" style={{ width: `${row.pct}%` }} />
                  </span>
                  <span className="mk-bar-value">{row.pct}</span>
                </div>
              ))}
            </div>

            <div className="mk-report-foot">
              <p className="mk-report-foot-label">Skills evidenced</p>
              <div className="mk-chips">
                {MATCH_REPORT.matched.map((skill) => (
                  <span className="mk-chip is-hit" key={skill}>
                    <IconCheck size={12} />
                    {skill}
                  </span>
                ))}
                <span className="mk-chip is-miss">
                  <span aria-hidden="true">&times;</span>
                  {MATCH_REPORT.missing}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ---------- Workflow ---------- */}
        <section className="mk-section is-dark" id="workflow">
          <SectionHead
            eyebrow="How it works"
            title="From posting to match score in four steps."
            lede="Each step produces something you can read and argue with, rather than a black box telling you it thinks you are a good fit."
          />

          <ol className="mk-steps">
            {STEPS.map((step, i) => (
              <li className="mk-step" key={step.n} data-reveal style={delay(i * 90)}>
                <span className="mk-step-n">{step.n}</span>
                <div className="mk-step-body">
                  <h3 className="mk-step-title">
                    {step.title}
                    {step.soon ? <span className="badge badge-amber">Coming soon</span> : null}
                  </h3>
                  <p className="mk-step-text">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* ---------- Capabilities ---------- */}
        <section className="mk-section" id="capabilities">
          <SectionHead
            eyebrow="Product"
            title="Everything the analysis is built on."
            lede="Each of these exists to remove one specific kind of guesswork from a job search."
          />

          <div className="mk-grid">
            {FEATURES.map(({ Icon, title, body, soon }, i) => (
              <article
                className="mk-card"
                key={title}
                data-reveal
                style={delay(Math.min(i, 5) * 70)}
              >
                <span className="mk-card-icon">
                  <Icon size={17} />
                </span>
                <h3 className="mk-card-title">
                  {title}
                  {soon ? <span className="badge badge-amber">Coming soon</span> : null}
                </h3>
                <p className="mk-card-text">{body}</p>
              </article>
            ))}
          </div>
        </section>

        {/* ---------- Privacy ---------- */}
        <section className="mk-section is-soft" id="privacy">
          <div className="mk-split">
            <SectionHead
              eyebrow="Privacy"
              title="Your resume does not have to leave your machine."
              lede="The analysis provider is pluggable, and the default one runs on your own hardware. Your resume is not shipped to a third-party API just to be scored."
            />

            <div className="mk-config" data-reveal>
              <p className="mk-config-label">Environment</p>
              {LOCAL_CONFIG.map((row) => (
                <div className="mk-config-row" key={row.key}>
                  <span className="mk-config-key">{row.key}</span>
                  <span className="mk-config-value">{row.value}</span>
                </div>
              ))}
              <p className="mk-config-note">
                Prefer a hosted model? The provider boundary is a single module, so swapping it
                does not touch the rest of the system.
              </p>
            </div>
          </div>
        </section>

        {/* ---------- Open source CTA ---------- */}
        <section className="mk-section is-dark">
          <div className="mk-cta" data-reveal="fade">
            <h2 className="mk-cta-title">Built in the open.</h2>
            <p className="mk-cta-lede">
              TailorUp is free and open source. Read the code, run it yourself, or contribute to
              the parts you want to change.
            </p>
            <div className="mk-actions mk-actions-center">
              <a
                className="btn btn-primary btn-lg"
                href={GITHUB_URL}
                target="_blank"
                rel="noreferrer"
              >
                <IconGitHub size={16} />
                View on GitHub
                <IconArrowRight size={16} />
              </a>
              <Link to={primaryTo} className="btn btn-ghost btn-lg">
                {signedIn ? 'Open dashboard' : 'Get started free'}
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="mk-footer">
        <div className="mk-footer-inner">
          <div className="mk-footer-brand">
            <Link to="/" className="brand">
              <span className="brand-mark">
                <IconLogo size={17} />
              </span>
              <span className="brand-name">TailorUp</span>
            </Link>
            <p className="mk-footer-tagline">
              Free and open-source job analysis. Runs locally, scores honestly.
            </p>
          </div>

          <nav className="mk-footer-col" aria-label="Product">
            <p className="mk-footer-title">Product</p>
            <Link to="/app/dashboard">Dashboard</Link>
            <Link to="/app/analyze">Analyse a job</Link>
            <Link to="/app/jobs">Jobs</Link>
            <Link to="/app/resumes">Resumes</Link>
          </nav>

          <nav className="mk-footer-col" aria-label="Project">
            <p className="mk-footer-title">Project</p>
            <a href="#workflow">How it works</a>
            <a href="#capabilities">Product</a>
            <a href="#privacy">Privacy</a>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">
              GitHub
            </a>
          </nav>
        </div>

        <div className="mk-footer-bottom">
          <span>&copy; {new Date().getFullYear()} TailorUp</span>
          <span>Built in the open.</span>
        </div>
      </footer>
    </div>
  )
}

export default LandingPage

