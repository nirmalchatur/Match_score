import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { IconBriefcase, IconLink, IconLogo, IconRadar, IconTarget, IconTrend, IconZap } from '../components/Icons'

/** Capabilities verified against the repository. Anything future is labelled. */
const FEATURES = [
  {
    Icon: IconLink,
    title: 'Job collection',
    body: 'Paste a Greenhouse URL. The posting is fetched and cleaned into readable text automatically.',
  },
  {
    Icon: IconRadar,
    title: 'JD analysis',
    body: 'Descriptions are parsed into a structured profile: required skills, experience, and responsibilities.',
  },
  {
    Icon: IconTarget,
    title: 'Resume matching',
    body: 'Your master resume is profiled the same way, so the two can be compared requirement by requirement.',
  },
  {
    Icon: IconTrend,
    title: 'Match scoring',
    body: 'Each posting gets a score out of 100 with the gaps spelled out, not a single opaque number.',
  },
  {
    Icon: IconBriefcase,
    title: 'Job history',
    body: 'Every analysis is saved to your workspace so you can revisit scores and pipeline state later.',
  },
  {
    Icon: IconZap,
    title: 'Private by default',
    body: 'Your resumes and job data are scoped to your account and never exposed to other users.',
  },
]

const FUTURE = [
  { title: 'Tailored resume versions', body: 'Generate a role-specific resume from your master document.' },
  { title: 'Application tracking', body: 'Move postings through saved, applied, interview, and offer.' },
  { title: 'Usage plans', body: 'Subscription tiers and per-account analysis limits.' },
]

const STEPS = [
  { n: '01', title: 'Upload your resume', body: 'Add a PDF once. We extract your skills, experience, and certifications.' },
  { n: '02', title: 'Add a job', body: 'Paste the URL of a posting you are interested in.' },
  { n: '03', title: 'Analyse', body: 'The pipeline collects, parses, and scores the posting automatically.' },
  { n: '04', title: 'Understand the match', body: 'See your score, the pipeline status, and where the gaps are.' },
]

const FLOW = ['Master Resume', 'Job URL', 'JD Analysis', 'Resume Match', 'Match Score']

const STACK = [
  'Django 6.1',
  'Django REST Framework',
  'React 19',
  'TypeScript',
  'Vite',
  'pypdf',
  'BeautifulSoup',
  'SQLite',
]

export function LandingPage() {
  const { status } = useAuth()

  return (
    <div className="landing">
      <div className="bg-fx" aria-hidden="true" />

      <header className="landing-nav">
        <Link to="/" className="brand">
          <span className="brand-mark">
            <IconLogo size={19} />
          </span>
          <span className="brand-name">TailorUp</span>
        </Link>

        <nav className="landing-links" aria-label="Marketing">
          <a href="#features">Product</a>
          <a href="#how">How it works</a>
          <a href="#stack">Technology</a>
          <a href="#docs">Docs</a>
        </nav>

        <div className="landing-cta">
          {status === 'authenticated' ? (
            <Link to="/app/dashboard" className="btn btn-primary btn-sm">
              Open dashboard
            </Link>
          ) : (
            <>
              <Link to="/login" className="btn btn-ghost btn-sm">
                Log in
              </Link>
              <Link to="/signup" className="btn btn-primary btn-sm">
                Get started
              </Link>
            </>
          )}
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="hero">
          <p className="hero-badge">
            <IconZap size={13} />
            Now in foundation release
          </p>

          <h1 className="hero-title">
            Tailor every application
            <br />
            around the job that <span className="gradient-text">matters</span>.
          </h1>

          <p className="hero-sub">
            TailorUp collects real job postings, parses them into structured requirements, and scores
            them against your master resume — so you know where you stand before you apply.
          </p>

          <div className="hero-actions">
            {status === 'authenticated' ? (
              <Link to="/app/dashboard" className="btn btn-primary">
                Open dashboard
                <IconZap size={16} />
              </Link>
            ) : (
              <Link to="/signup" className="btn btn-primary">
                Get started free
                <IconZap size={16} />
              </Link>
            )}
            <a href="#how" className="btn btn-ghost">
              See how it works
            </a>
          </div>

          <p className="hero-note">
            No credit card. Your resume stays private to your account.
          </p>
        </section>

        {/* Product flow */}
        <section className="flow" aria-label="How the pipeline works">
          {FLOW.map((step, index) => (
            <div className="flow-node" key={step}>
              <span className="flow-dot" />
              <span className="flow-label">{step}</span>
              {index < FLOW.length - 1 ? <span className="flow-line" aria-hidden="true" /> : null}
            </div>
          ))}
        </section>

        {/* Features */}
        <section className="section" id="features">
          <p className="eyebrow">Product</p>
          <h2 className="section-title">Everything you need to know if a job fits</h2>
          <p className="section-sub">
            Every capability below is implemented and running today.
          </p>

          <div className="bento">
            {FEATURES.map(({ Icon, title, body }) => (
              <div className="bento-card" key={title}>
                <span className="bento-icon">
                  <Icon size={18} />
                </span>
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            ))}
          </div>
        </section>


        {/* How it works */}
        <section className="section" id="how">
          <p className="eyebrow">How it works</p>
          <h2 className="section-title">Four steps from posting to score</h2>

          <div className="steps-grid">
            {STEPS.map((step) => (
              <div className="step-card" key={step.n}>
                <span className="step-n">{step.n}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Roadmap */}
        <section className="section">
          <p className="eyebrow">Roadmap</p>
          <h2 className="section-title">Coming next</h2>
          <p className="section-sub">
            These are planned, not yet built. They are listed so you know where the product is
            heading.
          </p>

          <div className="bento">
            {FUTURE.map((item) => (
              <div className="bento-card soon" key={item.title}>
                <span className="pill pill-accent">Coming soon</span>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Stack */}
        <section className="section" id="stack">
          <p className="eyebrow">Technology</p>
          <h2 className="section-title">Built on a Django + React stack</h2>
          <p className="section-sub">
            The exact libraries this project runs today — nothing aspirational.
          </p>

          <div className="stack-row">
            {STACK.map((tech) => (
              <span className="stack-chip" key={tech}>
                {tech}
              </span>
            ))}
          </div>
        </section>

        {/* Docs */}
        <section className="section" id="docs">
          <p className="eyebrow">Documentation</p>
          <h2 className="section-title">Read the project documentation</h2>
          <p className="section-sub">
            Setup, architecture, and the API surface are documented in the repository.
          </p>

          <div className="docs-grid">
            <a className="doc-card" href="/docs/README.md" target="_blank" rel="noreferrer">
              <h3>README</h3>
              <p>Setup, local development, and project structure.</p>
            </a>
            <a className="doc-card" href="/docs/ARCHITECTURE.md" target="_blank" rel="noreferrer">
              <h3>Architecture</h3>
              <p>Tenant model, data ownership, and API design.</p>
            </a>
            <a className="doc-card" href="/docs/API.md" target="_blank" rel="noreferrer">
              <h3>API reference</h3>
              <p>Every endpoint, its auth requirement, and its shape.</p>
            </a>
          </div>
        </section>

        {/* Final CTA */}
        <section className="cta-panel">
          <h2 className="cta-title">Build better applications with TailorUp.</h2>
          <p className="cta-sub">
            One resume. Every job. A smarter application workflow.
          </p>
          {status === 'authenticated' ? (
            <Link to="/app/dashboard" className="btn btn-primary">
              Open dashboard
            </Link>
          ) : (
            <Link to="/signup" className="btn btn-primary">
              Get started
            </Link>
          )}
        </section>
      </main>

      <footer className="landing-footer">
        <div className="footer-brand">
          <span className="brand-mark">
            <IconLogo size={17} />
          </span>
          <span className="brand-name">TailorUp</span>
        </div>

        <nav className="footer-links" aria-label="Footer">
          <a href="#features">Product</a>
          <a href="#how">How it works</a>
          <a href="#stack">Technology</a>
          <a href="#docs">Docs</a>
          <Link to="/login">Log in</Link>
        </nav>

        <p className="footer-copy">© {new Date().getFullYear()} TailorUp. All rights reserved.</p>
      </footer>
    </div>
  )
}

export default LandingPage

