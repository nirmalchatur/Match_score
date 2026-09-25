import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../lib/api'
import type { Job, Resume } from '../lib/types'

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
function useResource<T>(initial: T, fetcher: () => Promise<T>, errorMessage: string): Resource<T> {
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

  return { data, loading, error, refresh }
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
