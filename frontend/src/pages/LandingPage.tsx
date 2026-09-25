import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import {
  IconArrowRight,
  IconBriefcase,
  IconCheck,
  IconFile,
  IconGitHub,
  IconLayers,
  IconLink,
  IconLogo,
  IconRadar,
  IconTarget,
  IconTrend,
  IconZap,
} from '../components/Icons'

/* ---------- Hero pipeline ---------- */

const PIPELINE = [
  { label: 'Master resume', text: 'resume.pdf Â· 2 pages', tone: 'violet' },
  { label: 'Job posting URL', text: 'greenhouse.io/jobs/â€¦', tone: 'blue' },
  { label: 'Job analysis', text: '14 requirements Â· 8 skills extracted', tone: 'violet' },
  { label: 'Resume match', text: 'Profile compared against role', tone: 'violet' },
  { label: 'Match score', text: '82% Â· Strong Match', tone: 'green', score: '82%' },
]

const FACTS = [
  { value: 'Free', label: 'forever' },
  { value: 'Open', label: 'source' },
  { value: 'AI', label: 'powered' },
]

/* ---------- How it works ---------- */

const STEPS = [
  { n: '01', title: 'Upload Master Resume', body: 'Give TailorUp a baseline resume to work from.' },
  { n: '02', title: 'Add a Job', body: 'Paste a job posting URL to get started.' },
  {
    n: '03',
    title: 'Analyze the Role',
    body: 'Extract requirements, responsibilities, skills and experience.',
  },
  { n: '04', title: 'Understand Your Match', body: 'See where your profile aligns and where it falls short.' },
  {
    n: '05',
    title: 'Tailor Your Application',
    body: 'Use insights to improve your application.',
    soon: true,
  },
]

/* ---------- Features ---------- */

const FEATURES = [
  {
    Icon: IconRadar,
    title: 'Job Analysis',
    body: 'Extract skills, requirements, responsibilities, experience, and education from any job posting.',
    wide: true,
  },
  {
    Icon: IconTarget,
    title: 'Resume Matching',
    body: 'Compare your master resume against a role and understand alignment across every dimension.',
    wide: true,
  },
  { Icon: IconTrend, title: 'Skill Gap Analysis', body: 'Pinpoint the exact skills missing or underrepresented for each role.' },
  { Icon: IconLayers, title: 'Match Score', body: 'A precise percentage reflecting your overall fit with a role based on your resume.' },
  { Icon: IconBriefcase, title: 'Job Workspace', body: 'Keep all analyzed jobs organized in one clean, searchable workspace.' },
  {
    Icon: IconFile,
    title: 'Application Tracker',
    body: 'Track every application across its full lifecycle â€” from saved to offer.',
    soon: true,
  },
]

/* ---------- Architecture ---------- */

const ARCH = [
  { title: 'Job Extraction', body: ' â€” Playwright scrapes and parses job postings' },
  { title: 'JD Parsing', body: ' â€” LLM tooling extracts structured requirements' },
  { title: 'Resume Engine', body: ' â€” PDF parsing and semantic comparison' },
  { title: 'Match Analysis', body: ' â€” Score computation across multiple dimensions' },
]

/* ---------- Stack ---------- */

const STACK = [
  { name: 'React', desc: 'UI framework', tone: 'cyan', Icon: IconLink },
  { name: 'TypeScript', desc: 'Type safety', tone: 'blue', Icon: IconLayers },
  { name: 'Vite', desc: 'Build tooling', tone: 'violet', Icon: IconZap },
  { name: 'Python', desc: 'Backend runtime', tone: 'blue', Icon: IconLayers },
  { name: 'Django', desc: 'API framework', tone: 'green', Icon: IconBriefcase },
  { name: 'Playwright', desc: 'Job extraction', tone: 'green', Icon: IconBriefcase },
  { name: 'PostgreSQL', desc: 'Data layer', tone: 'blue', Icon: IconLayers },
  { name: 'LLM Tooling', desc: 'AI analysis', tone: 'violet', Icon: IconZap },
]

/* ---------- Docs ---------- */

const DOCS = [
  { Icon: IconFile, title: 'Project Overview', body: 'Understand what TailorUp does and how to get started.' },
  { Icon: IconLayers, title: 'Architecture', body: 'The full technical architecture of the platform.' },
  { Icon: IconZap, title: 'Development Setup', body: 'Run TailorUp locally in minutes.' },
  { Icon: IconLink, title: 'API Reference', body: 'Explore all available REST API endpoints.' },
  { Icon: IconRadar, title: 'Job Analysis Pipeline', body: 'How job descriptions are extracted and parsed.' },
  { Icon: IconTarget, title: 'Resume System', body: 'How master resumes are processed and compared.' },
]

/* ---------- Workspace mockup ---------- */

const MOCK_STATS = [
  { label: 'Jobs Analyzed', value: '9', hint: '+3 this week' },
  { label: 'Avg. Match', value: '75%', hint: 'Across all roles' },
  { label: 'Strong Matches', value: '2', hint: 'Score â‰¥ 80%' },
  { label: 'Applications', value: '12', hint: '3 in progress' },
]

const MOCK_ROWS = [
  { letter: 'A', title: 'Software Engineer', meta: 'Acme Corp Â· Remote', score: '82%', tone: 'success', label: 'Strong Match' },
  { letter: 'N', title: 'Backend Engineer', meta: 'Nimbus Systems Â· Bangalore', score: '76%', tone: 'info', label: 'Good Match' },
  { letter: 'S', title: 'Full-Stack Developer', meta: 'Stratum Labs Â· Hybrid', score: '68%', tone: 'warning', label: 'Needs Review' },
]

const MOCK_SKILLS = ['Python', 'AWS', 'React', 'Docker', 'SQL']

const GITHUB_URL = 'https://github.com'

export function LandingPage() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'

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
          <a href="#how">How it Works</a>
          <a href="#features">Features</a>
          <a href="#architecture">Technology</a>
          <a href="#docs">Docs</a>
        </nav>

        <div className="landing-cta">
          <a className="btn btn-ghost" href={GITHUB_URL} target="_blank" rel="noreferrer">
            <IconGitHub size={16} />
            GitHub
          </a>
          <Link to={signedIn ? '/app/dashboard' : '/login'} className="btn btn-ghost">
            {signedIn ? 'Dashboard' : 'Login'}
          </Link>
          <Link to={signedIn ? '/app/dashboard' : '/signup'} className="btn btn-primary">
            {signedIn ? 'Open dashboard' : 'Get Started'}
          </Link>
        </div>
      </header>

      <main>
        <section className="hero">
          <div>
            <span className="hero-badge">
              <span className="hero-badge-dot" />
              Open-source AI career workspace
            </span>

            <h1 className="hero-title">
              Tailor every application around{' '}
              <span className="gradient-text">the job that matters.</span>
            </h1>

            <p className="hero-sub">
              Analyze jobs, understand your resume match, discover skill gaps, and build better
              applications from one workspace.
            </p>

            <div className="hero-actions">
              <Link to={signedIn ? '/app/dashboard' : '/signup'} className="btn btn-primary">
                Get Started
                <IconArrowRight size={16} />
              </Link>
              <a className="btn btn-ghost" href="#how">
                Explore the workflow
              </a>
            </div>

            <div className="hero-facts">
              {FACTS.map((fact) => (
                <div key={fact.value}>
                  <div className="hero-fact-value">{fact.value}</div>
                  <div className="hero-fact-label">{fact.label}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="pipeline" aria-hidden="true">
            {PIPELINE.map((node) => (
              <div className="pipeline-card" data-tone={node.tone} key={node.label}>
                <span className={`pipeline-dot ${node.tone}`} />
                <div className="pipeline-body">
                  <div className="pipeline-label">{node.label}</div>
                  <div className="pipeline-text">{node.text}</div>
                </div>
                {node.score ? <span className="pipeline-score">{node.score}</span> : null}
              </div>
            ))}
          </div>
        </section>


        <section className="section center">
          <h2 className="section-title">Your entire job search workspace.</h2>
          <p className="section-sub">Everything in one place. Nothing out of view.</p>

          <div className="window" aria-hidden="true">
            <div className="window-bar">
              <span className="window-dots">
                <i className="red" />
                <i className="amber" />
                <i className="green" />
              </span>
              <span className="window-url">tailorup.dev/app/dashboard</span>
            </div>

            <div className="window-body">
              <div className="window-stats">
                {MOCK_STATS.map((stat) => (
                  <div className="window-stat" key={stat.label}>
                    <span className="window-stat-label">{stat.label}</span>
                    <span className="window-stat-value">{stat.value}</span>
                    <span className="window-stat-hint">{stat.hint}</span>
                  </div>
                ))}
              </div>

              <div className="window-recent">Recent Jobs</div>

              {MOCK_ROWS.map((row) => (
                <div className="window-row" key={row.title}>
                  <span className="window-avatar">{row.letter}</span>
                  <div className="window-row-body">
                    <div className="window-row-title">{row.title}</div>
                    <div className="window-row-meta">{row.meta}</div>
                  </div>
                  <span className={`pill pill-${row.tone}`}>{row.label}</span>
                  <span className={`window-score ${row.tone}`}>{row.score}</span>
                </div>
              ))}

              <div className="window-skills">
                <div className="window-recent">Software Engineer &middot; Acme Corp</div>
                <div className="skill-chips">
                  {MOCK_SKILLS.map((skill) => (
                    <span className="skill-chip has" key={skill}>
                      <IconCheck size={11} />
                      {skill}
                    </span>
                  ))}
                  <span className="skill-chip miss">&mdash; Kubernetes</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section center" id="how">
          <span className="section-pill">How It Works</span>
          <h2 className="section-title">
            From resume to insight
            <br />
            in five steps.
          </h2>

          <div className="steps-grid">
            {STEPS.map((step) => (
              <div className="step-card" key={step.n}>
                <span className="step-n">{step.n}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
                {step.soon ? <span className="badge badge-amber">Coming soon</span> : null}
              </div>
            ))}
          </div>
        </section>

        <section className="section center" id="features">
          <span className="section-pill">Features</span>
          <h2 className="section-title">Built for serious job seekers.</h2>
          <p className="section-sub">Every tool you need, none you don&rsquo;t.</p>

          <div className="bento">
            {FEATURES.map(({ Icon, title, body, wide, soon }) => (
              <div className={`bento-card${wide ? ' wide' : ''}`} key={title}>
                <span className="bento-icon">
                  <Icon size={16} />
                </span>
                <h3>
                  {title}
                  {soon ? <span className="badge badge-amber">Coming soon</span> : null}
                </h3>
                <p>{body}</p>
              </div>
            ))}
          </div>
        </section>


        <section className="section" id="architecture">
          <div className="arch-grid">
            <div>
              <span className="section-pill">Architecture</span>
              <h2 className="section-title">Built as an open-source AI career platform.</h2>
              <p className="section-sub">
                A React + TypeScript frontend communicates with a Django REST API that orchestrates
                a multi-stage job analysis pipeline &mdash; from extraction to match scoring.
              </p>

              <ul className="arch-list">
                {ARCH.map((item) => (
                  <li key={item.title}>
                    <span>
                      <strong>{item.title}</strong>
                      {item.body}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="arch-diagram" aria-hidden="true">
              <div className="arch-row">
                <div className="arch-node accent">
                  React + TypeScript
                  <small>Frontend Application</small>
                </div>
              </div>
              <div className="arch-arrow">&#9660;</div>
              <div className="arch-row">
                <div className="arch-node accent">
                  Django REST API
                  <small>Python &middot; Django REST Framework</small>
                </div>
              </div>
              <div className="arch-arrow">&#9660;</div>
              <div className="arch-row">
                <div className="arch-node accent">
                  Job Analysis Pipeline
                  <small>Playwright &middot; LLM Tooling</small>
                </div>
              </div>
              <div className="arch-arrow">&#9660;</div>
              <div className="arch-branches">
                <div className="arch-node">
                  Job Collector
                  <small>Playwright</small>
                </div>
                <div className="arch-node">
                  JD Parser
                  <small>LLM &middot; NLP</small>
                </div>
                <div className="arch-node">
                  Resume Engine
                  <small>PDF &middot; Matching</small>
                </div>
              </div>
              <div className="arch-row">
                <div className="arch-node green">Match Analysis &middot; Database</div>
              </div>
            </div>
          </div>
        </section>

        <section className="section center" id="stack">
          <span className="section-pill">Built with</span>
          <h2 className="section-title">A modern open-source stack.</h2>

          <div className="stack-grid">
            {STACK.map(({ name, desc, tone, Icon }) => (
              <div className="stack-card" key={name}>
                <span className={`stack-swatch ${tone}`}>
                  <Icon size={18} />
                </span>
                <span>
                  <span className="stack-name">{name}</span>
                  <span className="stack-desc">{desc}</span>
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="section center">
          <div className="oss-panel">
            <span className="section-pill">Open Source</span>
            <h2 className="section-title">Built in the open.</h2>
            <p className="section-sub">
              TailorUp is designed as a free, open-source project built to make smarter job
              applications accessible to everyone.
            </p>
            <div className="hero-actions">
              <a className="btn btn-primary" href={GITHUB_URL} target="_blank" rel="noreferrer">
                <IconGitHub size={16} />
                View on GitHub
                <IconArrowRight size={16} />
              </a>
              <a className="btn btn-ghost" href="#docs">
                Read the documentation
                <IconArrowRight size={16} />
              </a>
            </div>
            <div className="oss-note">Open source &middot; Contributions welcome</div>
          </div>
        </section>


        <section className="section center" id="docs">
          <span className="section-pill">Documentation</span>
          <h2 className="section-title">Everything you need to know.</h2>

          <div className="docs-grid">
            {DOCS.map(({ Icon, title, body }) => (
              <a className="doc-card" href="#docs" key={title}>
                <span className="bento-icon">
                  <Icon size={16} />
                </span>
                <span className="doc-body">
                  <h3>{title}</h3>
                  <p>{body}</p>
                </span>
                <IconArrowRight className="doc-arrow" size={16} />
              </a>
            ))}
          </div>
        </section>

        <section className="cta-panel">
          <h2 className="cta-title">
            Your next application
            <br />
            <span className="gradient-text">starts here.</span>
          </h2>
          <p className="cta-sub">
            Bring your resume. Bring the job description.
            <br />
            Let TailorUp show you where they align.
          </p>
          <div className="hero-actions">
            <Link to={signedIn ? '/app/dashboard' : '/signup'} className="btn btn-primary">
              {signedIn ? 'Open dashboard' : 'Get Started'}
              <IconArrowRight size={16} />
            </Link>
          </div>
          <div className="cta-note">Free. Open source. No credit card needed.</div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="footer-grid">
          <div>
            <div className="footer-brand">
              <span className="brand-mark">
                <IconLogo size={17} />
              </span>
              <span className="brand-name">TailorUp</span>
            </div>
            <p className="footer-tagline">Free and open-source AI career workspace.</p>
          </div>

          <div className="footer-col">
            <div className="footer-col-title">Product</div>
            <ul>
              <li>
                <Link to="/app/dashboard">Dashboard</Link>
              </li>
              <li>
                <Link to="/app/analyze">Job Analysis</Link>
              </li>
              <li>
                <Link to="/app/resumes">Resumes</Link>
              </li>
              <li>
                <Link to="/app/applications">Applications</Link>
              </li>
            </ul>
          </div>

          <div className="footer-col">
            <div className="footer-col-title">Resources</div>
            <ul>
              <li>
                <a href="#docs">Documentation</a>
              </li>
              <li>
                <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                  GitHub
                </a>
              </li>
              <li>
                <a href="#architecture">Architecture</a>
              </li>
            </ul>
          </div>

          <div className="footer-col">
            <div className="footer-col-title">Project</div>
            <ul>
              <li>
                <a href="#how">About</a>
              </li>
              <li>
                <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                  Open Source
                </a>
              </li>
              <li>
                <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                  Contributing
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="footer-bottom">
          <span>&copy; {new Date().getFullYear()} TailorUp</span>
          <span>Built in the open.</span>
        </div>
      </footer>
    </div>
  )
}

export default LandingPage

