import type { AnalyzeResponse, Job, JobQuery, MasterResume, Resume } from './types'

/**
 * API base URL.
 * Defaults to a relative `/api` prefix so the Vite dev proxy (and any
 * reverse proxy in production) can forward to Django without CORS.
 * Override with VITE_API_URL for a cross-origin backend.
 */
const BASE_URL = (import.meta.env.VITE_API_URL || '/api').replace(/\/+$/, '')

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Pull a human-readable message out of the various error shapes Django/DRF return. */
function extractError(payload: unknown, fallback: string): string {
  if (typeof payload === 'string' && payload.trim()) {
    return payload
  }

  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>

    for (const key of ['error', 'detail', 'message'] as const) {
      const value = record[key]
      if (typeof value === 'string' && value.trim()) {
        return value
      }
    }

    // DRF field errors look like { url: ["This field is required."] }
    for (const value of Object.values(record)) {
      if (Array.isArray(value) && typeof value[0] === 'string') {
        return value[0]
      }
    }
  }

  return fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError('Cannot reach the API server. Is the backend running on port 8000?', 0)
  }

  const text = await response.text()
  let payload: unknown = null

  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = text
    }
  }

  if (!response.ok) {
    throw new ApiError(extractError(payload, `Request failed (${response.status})`), response.status)
  }

  return payload as T
}

export const api = {
  listJobs({ q, status, sort }: JobQuery = {}): Promise<Job[]> {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (status) params.set('status', status)
    if (sort) params.set('sort', sort)

    const qs = params.toString()
    return request<Job[]>(`/jobs/${qs ? `?${qs}` : ''}`)
  },

  analyzeJob(url: string): Promise<AnalyzeResponse> {
    return request<AnalyzeResponse>('/jobs/analyze/', {
      method: 'POST',
      body: JSON.stringify({ url }),
    })
  },

  listResumes(): Promise<Resume[]> {
    return request<Resume[]>('/resumes/')
  },

  /** The master-resume endpoint 404s when none is configured — that is not an error. */
  async getMasterResume(): Promise<MasterResume> {
    try {
      const resume = await request<Resume>('/resumes/master/')
      return { resume, hasMaster: true }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return { resume: null, hasMaster: false }
      }
      throw error
    }
  },

  /**
   * Absolute URL for a stored file.
   *
   * DRF returns FileField values that are either already absolute, or
   * root-relative to the API origin (e.g. "/resumes/master_resume.pdf").
   * Only bare, unrooted paths get the API prefix applied.
   */
  fileUrl(path: string): string {
    if (/^https?:\/\//i.test(path)) return path
    if (path.startsWith('/')) return path
    return `${BASE_URL}/${path}`
  },
}
