import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../lib/api'
import type { Application, ApplicationStatus, DashboardStats, Job, Resume } from '../lib/types'

function toMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

type Resource<T> = {
  data: T
  loading: boolean
  error: string
  refresh: () => void
}

/**
 * Fetches on mount and exposes a manual refresh.
 *
 * The mount effect awaits before touching state, so it never triggers a
 * cascading render. A refresh keeps the previous error visible until the new
 * result lands, which avoids the error banner flickering on every poll.
 */
function useResource<T>(
  initial: T,
  fetcher: () => Promise<T>,
  errorMessage: string,
): Resource<T> & { setData: React.Dispatch<React.SetStateAction<T>> } {
  const [data, setData] = useState<T>(initial)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Keep the latest fetcher without making it an effect dependency.
  const fetcherRef = useRef(fetcher)

  useEffect(() => {
    fetcherRef.current = fetcher
  }, [fetcher])

  useEffect(() => {
    let cancelled = false

    const start = async () => {
      try {
        const result = await fetcherRef.current()
        if (cancelled) return
        setData(result)
        setError('')
      } catch (err) {
        if (!cancelled) setError(toMessage(err, errorMessage))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void start()
    return () => {
      cancelled = true
    }
  }, [errorMessage])

  const refresh = useCallback(() => {
    setLoading(true)

    const start = async () => {
      try {
        const result = await fetcherRef.current()
        setData(result)
        setError('')
      } catch (err) {
        setError(toMessage(err, errorMessage))
      } finally {
        setLoading(false)
      }
    }

    void start()
  }, [errorMessage])

  return { data, loading, error, refresh, setData }
}

const fetchJobs = () => api.listJobs()

const fetchResumes = async (): Promise<{ resumes: Resume[]; master: Resume | null }> => {
  const [list, masterResult] = await Promise.all([api.listResumes(), api.getMasterResume()])
  return { resumes: list, master: masterResult.resume }
}

/** Jobs list plus API reachability, derived from the last request outcome. */
export function useJobs() {
  const { data, loading, error, refresh } = useResource<Job[]>(
    [],
    fetchJobs,
    'Unable to load jobs.',
  )

  return { jobs: data, loading, error, online: error === '', refresh }
}

/** Resumes list plus the configured master resume. */
export function useResumes() {
  const { data, loading, error, refresh } = useResource(
    { resumes: [] as Resume[], master: null as Resume | null },
    fetchResumes,
    'Unable to load resumes.',
  )

  return {
    resumes: data.resumes,
    master: data.master,
    loading,
    error,
    refresh,
  }
}


/**
 * The application tracker list plus the dashboard's aggregate metrics.
 *
 * Both come from one hook so the tracker and the dashboard tiles can never show
 * numbers captured at different moments. Mutations patch the cache in place so
 * the UI reacts immediately, then refresh in the background to pick up the new
 * aggregates (a status change moves the dashboard counters too).
 */
export function useApplications() {
  const { data, loading, error, refresh, setData } = useResource<{
    applications: Application[]
    stats: DashboardStats | null
  }>(
    { applications: [], stats: null },
    async () => {
      const [applications, stats] = await Promise.all([
        api.listApplications(),
        api.dashboardStats(),
      ])
      return { applications, stats }
    },
    'Unable to load applications.',
  )

  /** Replace one row and recompute the cached aggregates. */
  const replaceOne = useCallback(
    (updated: Application) => {
      setData((current) => ({
        applications: current.applications.map((item) =>
          item.id === updated.id ? updated : item,
        ),
        stats: current.stats,
      }))
    },
    [setData],
  )

  const create = useCallback(
    async (jobId: number, tailoredResumeId?: number | null) => {
      const created = await api.createApplication({
        job: jobId,
        tailored_resume: tailoredResumeId ?? null,
      })
      setData((current) => ({
        applications: [created, ...current.applications],
        stats: current.stats,
      }))
      void refresh()
      return created
    },
    [refresh, setData],
  )

  const setStatus = useCallback(
    async (id: number, status: ApplicationStatus) => {
      const updated = await api.setApplicationStatus(id, status)
      replaceOne(updated)
      // A status change moves the dashboard counters, so pull the new totals.
      void refresh()
      return updated
    },
    [refresh, replaceOne],
  )

  const updateNotes = useCallback(
    async (id: number, notes: string) => {
      const updated = await api.updateApplication(id, { notes })
      replaceOne(updated)
      return updated
    },
    [replaceOne],
  )

  const remove = useCallback(
    async (id: number) => {
      await api.deleteApplication(id)
      setData((current) => ({
        applications: current.applications.filter((item) => item.id !== id),
        stats: current.stats,
      }))
      void refresh()
    },
    [refresh, setData],
  )

  return {
    applications: data.applications,
    stats: data.stats,
    loading,
    error,
    refresh,
    create,
    setStatus,
    updateNotes,
    remove,
  }
}
