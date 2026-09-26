import type {
  AnalyzeResponse,
  AuthResponse,
  Job,
  JobQuery,
  MasterResume,
  MeResponse,
  Resume,
  TailoringResponse,
  TailoringResult,
  TailoringStatus,
  UserProfile,
} from './types'

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

/** True when the failure means "you are signed out". */
export function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403)
}

/** Read Django's CSRF cookie so unsafe requests can be authenticated. */
function getCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : ''
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])

/** Pull a human-readable message out of the various error shapes Django/DRF returns. */
function extractError(payload: unknown, fallback: string): string {
  if (typeof payload === 'string' && payload.trim()) {
    return payload
  }

  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>

    for (const key of ['error', 'detail', 'message', 'non_field_errors'] as const) {
      const value = record[key]
      if (typeof value === 'string' && value.trim()) {
        return value
      }
      if (Array.isArray(value) && typeof value[0] === 'string') {
        return value[0]
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
  const method = (init?.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init?.headers as Record<string, string> | undefined),
  }

  // Only set a JSON content type for non-multipart bodies; FormData must let
  // the browser set its own boundary.
  if (!(init?.body instanceof FormData) && init?.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  // Django requires the CSRF header on unsafe session-authenticated requests.
  if (!SAFE_METHODS.has(method)) {
    const token = getCookie('csrftoken')
    if (token) headers['X-CSRFToken'] = token
  }

  let response: Response

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers,
      // The session cookie is HttpOnly, so it must be sent explicitly.
      credentials: 'include',
    })
  } catch {
    throw new ApiError('Cannot reach the API server. Is the backend running on port 8000?', 0)
  }

  if (response.status === 204) {
    return undefined as T
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
  /* ---------- Auth ---------- */

  me(): Promise<MeResponse> {
    return request<MeResponse>('/auth/me/')
  },

  login(email: string, password: string): Promise<AuthResponse> {
    return request<AuthResponse>('/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },

  register(email: string, password: string, fullName?: string): Promise<AuthResponse> {
    return request<AuthResponse>('/auth/register/', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName || '' }),
    })
  },

  logout(): Promise<void> {
    return request<void>('/auth/logout/', { method: 'POST' })
  },

  getProfile(): Promise<UserProfile> {
    return request<UserProfile>('/auth/profile/')
  },

  updateProfile(patch: Partial<UserProfile>): Promise<UserProfile> {
    return request<UserProfile>('/auth/profile/', {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  },

  /* ---------- Jobs ---------- */

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

  /* ---------- Resumes ---------- */

  listResumes(): Promise<Resume[]> {
    return request<Resume[]>('/resumes/')
  },

  /** Upload a PDF. Sent as multipart so the browser sets the boundary. */
  uploadResume(form: FormData): Promise<Resume> {
    return request<Resume>('/resumes/', {
      method: 'POST',
      body: form,
    })
  },

  setMasterResume(id: number): Promise<Resume> {
    return request<Resume>(`/resumes/${id}/set-master/`, { method: 'POST' })
  },

  deleteResume(id: number): Promise<{ deleted: boolean; had_master: boolean }> {
    return request<{ deleted: boolean; had_master: boolean }>(`/resumes/${id}/`, {
      method: 'DELETE',
    })
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
   * root-relative to the API origin (e.g. "/media/resumes/master.pdf").
   * Only bare, unrooted paths get the API prefix applied.
   */
  fileUrl(path: string): string {
    if (/^https?:\/\//i.test(path)) return path
    if (path.startsWith('/')) return path
    return `${BASE_URL}/${path}`
  },

  /* ---------- AI tailoring ---------- */

  /** Is tailoring available at all? Used to disable the button up front. */
  tailoringStatus(): Promise<TailoringStatus> {
    return request<TailoringStatus>('/resumes/tailor/status/')
  },

  /**
   * Tailor the master resume for a job.
   *
   * Only the job id is sent: the resume, the job description and the match
   * analysis are all loaded server-side from the signed-in account's own rows.
   */
  tailorResume(jobId: number): Promise<TailoringResponse> {
    return request<TailoringResponse>('/resumes/tailor/', {
      method: 'POST',
      body: JSON.stringify({ job_id: jobId }),
    })
  },

  /**
   * Save a reviewed tailoring as a new resume version.
   *
   * The server re-validates `result` against the master resume before writing,
   * so this is not a trust boundary in either direction.
   */
  saveTailoredResume(jobId: number, result: TailoringResult, provider?: string): Promise<Resume> {
    return request<Resume>('/resumes/tailor/save/', {
      method: 'POST',
      body: JSON.stringify({ job_id: jobId, result, provider: provider || '' }),
    })
  },
}

