import { useEffect, useMemo, useState } from 'react'
import { ApiError, api } from '../lib/api'
import type { JobSummary } from '../lib/types'
import { IconRefresh, IconSearch } from '../components/Icons'
import { JobDetail } from '../components/JobDetail'
import { JobRow } from '../components/JobRow'
import { Alert, EmptyState, JobRowSkeleton } from '../components/primitives'

const STATUSES = [
  { value: '', label: 'All statuses' },
  { value: 'READY', label: 'Ready' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'RUNNING', label: 'Running' },
  { value: 'PENDING', label: 'Pending' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'SKIPPED', label: 'Skipped' },
]

const SORTS = [
  { value: '-created_at', label: 'Newest first' },
  { value: 'created_at', label: 'Oldest first' },
  { value: '-match_score', label: 'Highest match' },
  { value: 'match_score', label: 'Lowest match' },
]

export function JobsPage() {
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('-created_at')

  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [selected, setSelected] = useState<JobSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Debounce keystrokes so we do not fire a request per character.
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    let cancelled = false

    const run = async () => {
      setLoading(true)
      setError('')
      try {
        const data = await api.listJobs({ q: debounced, status, sort })
        if (cancelled) return
        setJobs(data)
        setSelected((current) => {
          if (current && data.some((job) => job.id === current.id)) {
            return data.find((job) => job.id === current.id) ?? null
          }
          return data[0] ?? null
        })
      } catch (err) {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Unable to load jobs. Please try again.')
        setJobs([])
        setSelected(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [debounced, status, sort])

  const summary = useMemo(() => {
    const scored = jobs.filter((job) => job.match_score != null)
    const average = scored.length
      ? scored.reduce((sum, job) => sum + (job.match_score ?? 0), 0) / scored.length
      : null
    return { count: jobs.length, average, scored: scored.length }
  }, [jobs])

  const clearFilters = () => {
    setSearch('')
    setDebounced('')
    setStatus('')
  }

  const summaryLine = loading
    ? 'Loading…'
    : `${summary.count} job${summary.count === 1 ? '' : 's'}${
        summary.scored > 0 ? ` · average match ${Math.round(summary.average ?? 0)}%` : ''
      }`


  return (
    <div className="page stack">
      <section className="card">
        <div className="card-body">
          <div className="form-row">
            <div className="field">
              <IconSearch size={17} />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by title, company, or URL…"
                aria-label="Search jobs"
              />
            </div>

            <select
              className="select"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              aria-label="Filter by status"
            >
              {STATUSES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>

            <select
              className="select"
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              aria-label="Sort jobs"
            >
              {SORTS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>

            <button
              type="button"
              className="btn btn-ghost btn-icon"
              onClick={clearFilters}
              disabled={!search && !status}
              aria-label="Clear filters"
              title="Clear filters"
            >
              <IconRefresh size={16} />
            </button>
          </div>

          <div className="stat-hint" style={{ marginTop: 12 }}>
            {summaryLine}
          </div>
        </div>
      </section>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <section className="grid-dashboard">
        <div className="card sticky-col">
          <div className="card-head">
            <h3>Jobs</h3>
            <div className="card-head-actions">
              <span className="pill">{jobs.length}</span>
            </div>
          </div>

          {loading ? (
            <div className="job-list">
              {Array.from({ length: 5 }).map((_, index) => (
                <JobRowSkeleton key={index} />
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState
              title="No matches"
              description={
                search || status
                  ? 'No jobs match the current filters. Try clearing them.'
                  : 'Analyze a job URL to populate this list.'
              }
            />
          ) : (
            <div className="job-list">
              {jobs.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  selected={selected?.id === job.id}
                  onSelect={setSelected}
                />
              ))}
            </div>
          )}
        </div>

        <div>
          {selected ? (
            <JobDetail job={selected} />
          ) : (
            <div className="card">
              <EmptyState
                title="Nothing selected"
                description="Select a job to see its full analysis."
              />
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default JobsPage
