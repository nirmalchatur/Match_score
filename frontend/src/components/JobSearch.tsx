import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, isAuthError } from '../lib/api'
import type { JobSearchHit, JobSearchResponse } from '../lib/types'
import { IconSearch } from './Icons'

/** The server's 409 body, narrowed to the one code this screen handles. */
type SearchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; data: JobSearchResponse }
  | { kind: 'needs_resume'; message: string }
  | { kind: 'error'; message: string }

/** Score bands, so a number is not left for the user to interpret. */
function scoreTone(score: number): string {
  if (score >= 75) return 'js-strong'
  if (score >= 50) return 'js-good'
  if (score >= 35) return 'js-fair'
  return 'js-weak'
}

function scoreLabel(score: number): string {
  if (score >= 75) return 'Strong match'
  if (score >= 50) return 'Good match'
  if (score >= 35) return 'Partial match'
  return 'Weak match'
}

/**
 * The empty and error states.
 *
 * Each says something different and actionable, because the three causes look
 * identical in the network tab and produce three different next steps for the
 * user: upload a resume, add some jobs, or widen the search.
 */
function EmptyState({ state, onRetry }: { state: SearchState; onRetry: () => void }) {
  if (state.kind === 'needs_resume') {
    return (
      <div className="js-empty">
        <strong>Add a master resume first</strong>
        <p>{state.message}</p>
        <p className="js-empty-hint">
          Matching works by comparing your resume's skills against the job
          description, so there is nothing to compare until one exists.
        </p>
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <div className="js-empty">
        <strong>Could not run the search</strong>
        <p>{state.message}</p>
        <button type="button" className="btn btn-ghost" onClick={onRetry}>
          Try again
        </button>
      </div>
    )
  }

  if (state.kind !== 'ready') return null

  const { data } = state

  if (data.reason === 'no_skills') {
    return (
      <div className="js-empty">
        <strong>Your resume has no extracted skills yet</strong>
        <p>
          &ldquo;{data.resume.name}&rdquo; was uploaded but has not been
          processed, so there is nothing to match against. Re-upload it or let
          the analysis finish.
        </p>
      </div>
    )
  }

  if (data.total_jobs === 0) {
    return (
      <div className="js-empty">
        <strong>No analysed jobs yet</strong>
        <p>
          Add a job posting and let it finish analysing. This search ranks the
          jobs already in your account against your resume.
        </p>
      </div>
    )
  }

  return (
    <div className="js-empty">
      <strong>Nothing scored above the usefulness bar</strong>
      <p>
        {data.examined} of your {data.total_jobs} jobs were checked. None share
        enough skills with your resume to be worth surfacing.
      </p>
      <p className="js-empty-hint">
        Adding more postings will widen this. Jobs that have not finished
        analysing are skipped rather than ranked.
      </p>
    </div>
  )
}

/** One ranked result. */
function ResultRow({ hit }: { hit: JobSearchHit }) {
  return (
    <li className="js-hit">
      <div className="js-hit-head">
        <div className="js-hit-title">
          <a href={hit.url} target="_blank" rel="noopener noreferrer">
            {hit.title}
          </a>
          <span className="js-hit-company">{hit.company}</span>
        </div>
        <div
          className={`js-score ${scoreTone(hit.score)}`}
          title={scoreLabel(hit.score)}
        >
          <strong>{Math.round(hit.score)}</strong>
          <span>{scoreLabel(hit.score)}</span>
        </div>
      </div>

      <p className="js-hit-headline">{hit.headline}</p>

      {hit.matched_skills.length ? (
        <ul className="js-chips">
          {hit.matched_skills.slice(0, 6).map((skill) => (
            <li key={skill} className="js-chip js-chip-match">
              {skill}
            </li>
          ))}
          {hit.matched_skills.length > 6 ? (
            <li className="js-chip js-chip-more">
              +{hit.matched_skills.length - 6}
            </li>
          ) : null}
        </ul>
      ) : null}

      {hit.missing_skills.length ? (
        <ul className="js-chips">
          {hit.missing_skills.slice(0, 4).map((skill) => (
            <li key={skill} className="js-chip js-chip-missing">
              {skill}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="js-hit-meta">
        {hit.location ? <span>{hit.location}</span> : null}
        <span>{hit.source}</span>
      </div>
    </li>
  )
}

/**
 * Job search: this account's jobs, ranked against the master resume.
 *
 * Searches on submit rather than per keystroke. Scoring runs on the server for
 * every candidate job, and a request per character would queue several of
 * those and show results for a prefix the user has already moved past. The
 * AbortController covers the case that actually happens in practice: the user
 * submits, then immediately submits something else.
 */
export function JobSearch() {
  const [query, setQuery] = useState('')
  const [skills, setSkills] = useState('')
  const [applied, setApplied] = useState({ q: '', skills: [] as string[] })
  const [state, setState] = useState<SearchState>({ kind: 'idle' })

  // Aborted on unmount and on a new submit. Without this, a slow first
  // response can land after a fast second one and overwrite the newer results.
  const inFlight = useRef<AbortController | null>(null)

  const run = useCallback(async (q: string, skillList: string[]) => {
    inFlight.current?.abort()
    const controller = new AbortController()
    inFlight.current = controller

    setState({ kind: 'loading' })

    try {
      const data = await api.searchJobs({ q, skills: skillList })
      if (controller.signal.aborted) return
      setState({ kind: 'ready', data })
    } catch (err) {
      if (controller.signal.aborted) return

      // The 409 is the documented "no master resume" answer, not a failure.
      if (err instanceof ApiError && err.status === 409) {
        setState({
          kind: 'needs_resume',
          message: err.message,
        })
        return
      }

      if (isAuthError(err)) return

      setState({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Unknown error.',
      })
    }
  }, [])

  // Load once on mount so the panel is useful before anyone types.
  useEffect(() => {
    void run('', [])
    return () => inFlight.current?.abort()
  }, [run])

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    const skillList = skills
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean)
    setApplied({ q: query.trim(), skills: skillList })
    void run(query.trim(), skillList)
  }

  const data = state.kind === 'ready' ? state.data : null

  return (
    <section className="js-panel" aria-label="Job search">
      <form className="js-form" onSubmit={onSubmit}>
        <div className="js-field">
          <label htmlFor="js-query">Search your jobs</label>
          <div className="js-input-wrap">
            <IconSearch size={15} />
            <input
              id="js-query"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Role, company or keyword"
            />
          </div>
        </div>

        <div className="js-field">
          <label htmlFor="js-skills">Skills</label>
          <input
            id="js-skills"
            type="text"
            value={skills}
            onChange={(event) => setSkills(event.target.value)}
            placeholder="python, django"
          />
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          disabled={state.kind === 'loading'}
        >
          {state.kind === 'loading' ? <span className="spinner" /> : null}
          Search
        </button>
      </form>

      {data ? (
        <p className="js-summary">
          {data.results.length} match{data.results.length === 1 ? '' : 'es'} for
          &ldquo;{data.resume.name}&rdquo; ({data.resume.skills} skills)
          {data.truncated ? (
            <span className="js-summary-note">
              {' '}Showing the best of {data.matched_filter} candidates.
            </span>
          ) : null}
        </p>
      ) : null}

      <EmptyState state={state} onRetry={() => void run(applied.q, applied.skills)} />

      {data && data.results.length ? (
        <ul className="js-results">
          {data.results.map((hit) => (
            <ResultRow key={hit.job_id} hit={hit} />
          ))}
        </ul>
      ) : null}
    </section>
  )
}

export default JobSearch
