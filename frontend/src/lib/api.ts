import type {
  AiKeyStatus,
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
  TailoringProgress,
  QualitiesResponse,
  QualitySelection,
  UserProfile,
  Application,
  ApplicationStatus,
  ApplicationSummary,
  DashboardStats,
  Notification,
  NotificationListResponse,
  NotificationPreferences,
  JobSearchResponse,
  SecurityOverview,
} from './types'

/**
 * API base URL.
 * Defaults to a relative `/api` prefix so the Vite dev proxy can forward to
 * Django without CORS. Override with VITE_API_URL for a cross-origin backend.
 */
const RAW_BASE_URL = (import.meta.env.VITE_API_URL || '').trim()
const BASE_URL = (RAW_BASE_URL || '/api').replace(/\/+$/, '')

/**
 * True when a production bundle is still calling its own origin.
 *
 * That means `VITE_API_URL` was not set at build time, so the request never
 * leaves the browser's host. On Vercel that host is a CDN, and it answers
 * with its own 404/405 -- an error that looks like a broken API but is
 * really a misconfigured build. Catching it here turns a baffling network
 * tab into a message that names the actual fix.
 */
const API_URL_MISSING = import.meta.env.PROD && !RAW_BASE_URL

const API_URL_MISSING_MESSAGE =
  'This deployment is not connected to the API. ' +
  'VITE_API_URL was not set when the site was built, so requests are going ' +
  'to the static site instead of Django. ' +
  'Set VITE_API_URL on the Vercel project (including the trailing /api) ' +
  'and redeploy.'

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

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])

/**
 * The CSRF token, held in memory.
 *
 * It used to be read from `document.cookie`, which works when the SPA and
 * the API share an origin. They do not: the page is on Vercel and the
 * `csrftoken` cookie is set on the Render host, and a page can only read
 * cookies belonging to its own domain. `credentials: 'include'` makes the
 * browser *send* those cookies, but it does nothing to make them readable
 * by script, so the header silently went out unset and every mutating
 * request died with "CSRF token missing".
 *
 * The token is therefore fetched from the API and kept here. A CSRF token
 * is not a secret -- it is echoed back in the header, which is the whole
 * point of the double-submit pattern -- so memory is an appropriate place
 * for it. It is refetched whenever a request is rejected for a stale token.
 */
let csrfToken: string | null = null

async function fetchCsrfToken(): Promise<string> {
  const response = await fetch(`${BASE_URL}/auth/csrf/`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new ApiError(
      `Could not obtain a CSRF token (HTTP ${response.status}).`,
      response.status,
    )
  }
  const payload = await response.json()
  csrfToken = payload.csrf_token || null
  if (!csrfToken) {
    throw new ApiError('The API did not return a CSRF token.', 0)
  }
  return csrfToken
}

/** Read the filename the server chose from Content-Disposition. */
function filenameFromDisposition(header: string | null, fallback: string): string {
  const match = header?.match(/filename="?([^"]+)"?/i)
  return match?.[1] || fallback
}



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
  return attempt<T>(path, init, true)
}

async function attempt<T>(
  path: string,
  init: RequestInit | undefined,
  allowTokenRetry: boolean,
): Promise<T> {
  // Fail before touching the network, and before fetching a CSRF token.
  //
  // A relative BASE_URL in production can only ever reach the CDN, so the round
  // trip could only ever return a 404/405 that misattributes the problem to
  // the API. This check used to sit below the CSRF fetch, which is precisely
  // the request that can fail: an unsafe call spent a round trip on
  // `/auth/csrf/` against the static host, got a 404, and reported
  // "Could not obtain a CSRF token (HTTP 404)" -- a message that points at the
  // backend, when the real cause was a missing VITE_API_URL and the backend was
  // never involved. Every retry repeated it.
  if (API_URL_MISSING) {
    throw new ApiError(API_URL_MISSING_MESSAGE, 0)
  }

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
  // It is fetched rather than read from document.cookie, which is empty for a
  // page on a different origin from the API.
  if (!SAFE_METHODS.has(method)) {
    if (!csrfToken) {
      await fetchCsrfToken()
    }
    if (csrfToken) headers['X-CSRFToken'] = csrfToken
  }

  let response: Response

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers,
      // The session cookie is HttpOnly, so it must be sent explicitly.
      credentials: 'include',
    })
  } catch (error) {
    // A timeout is not a CORS rejection and must not be reported as one. The
    // generic message below blames the server or the browser's preflight
    // handling, which is actively misleading when the real cause is that *we*
    // gave up waiting -- and it would send someone to debug CORS headers for a
    // request that was simply cancelled on schedule.
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError(
        'The server did not respond in time. It may be starting up — please try again.',
        0,
      )
    }

    // A failed fetch is genuinely ambiguous: the browser reports a CORS
    // rejection exactly like a dead network, because it refuses to hand the
    // response to the page at all. Saying only "cannot reach the API" sends
    // people to restart a backend that is in fact serving requests perfectly
    // well -- the real cause is almost always CORS.
    throw new ApiError(
      `Cannot reach the API at ${BASE_URL}.\n` +
        'Either the backend is down, or the browser blocked the response ' +
        'because the API did not return an Access-Control-Allow-Origin ' +
        'header for this origin.\n\n' +
        'To tell them apart, run this in the browser console:\n' +
        `  fetch('${BASE_URL}/auth/me/').then(r =>\n` +
        '    console.log(r.status)).catch(() =>\n' +
        "    console.log('blocked or offline'))\n\n" +
        'If the console shows a status, the backend is fine and the issue is ' +
        'CORS_ALLOWED_ORIGINS on the server. If it logs "blocked or offline", ' +
        'the request never completed.',
      0,
    )
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
    // Django rotates the CSRF token on login, so a token cached before
    // signing in is stale afterwards. Refetch once and replay; a second
    // failure is a real error and is reported as one.
    if (
      response.status === 403 &&
      allowTokenRetry &&
      !SAFE_METHODS.has(method)
    ) {
      csrfToken = null
      await fetchCsrfToken()
      return attempt<T>(path, init, false)
    }

    throw new ApiError(extractError(payload, `Request failed (${response.status})`), response.status)
  }

  return payload as T
}

export const api = {
  /* ---------- Auth ---------- */

  /**
   * The current account, or an unauthenticated marker.
   *
   * `timeoutMs` bounds the wait. The bootstrap call passes one because this
   * endpoint gates first paint, and an unbounded request against a host that
   * is waking from zero instances leaves the user staring at a spinner for
   * the best part of a minute with no way out. Omit it for the background
   * reconciliations, where there is nothing to protect the user from.
   */
  me(timeoutMs?: number): Promise<MeResponse> {
    const init: RequestInit = timeoutMs ? { signal: AbortSignal.timeout(timeoutMs) } : {}
    return request<MeResponse>('/auth/me/', init)
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

  /* ---------- Job search ---------- */

  /**
   * Jobs this account has collected, ranked against the current master resume.
   *
   * `skills` is sent as a comma-separated list because that is how people
   * phrase a search ("python, django") and splitting it server-side is more
   * predictable than making each caller build the query string.
   */
  searchJobs(params: {
    q?: string
    skills?: string[]
    limit?: number
  } = {}): Promise<JobSearchResponse> {
    const query = new URLSearchParams()
    if (params.q) query.set('q', params.q)
    if (params.skills?.length) query.set('skills', params.skills.join(','))
    if (params.limit) query.set('limit', String(params.limit))

    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<JobSearchResponse>(`/jobs/search/${suffix}`)
  },

  /* ---------- Security ---------- */

  /** Live sessions and recent security events for the signed-in account. */
  getSecurityOverview(): Promise<SecurityOverview> {
    return request<SecurityOverview>('/auth/security/')
  },

  /**
   * Sign out every session except this one.
   *
   * Named for what it does rather than "revoke all": the caller stays signed in
   * on the tab that pressed the button, which is the behaviour that makes it
   * safe to offer as a one-click remedy.
   */
  revokeOtherSessions(): Promise<{ revoked: number }> {
    return request<{ revoked: number }>('/auth/security/revoke-others/', {
      method: 'POST',
    })
  },

  /**
   * Change the password. Requires the current one, which is what stops a
   * stolen session from becoming a permanent takeover.
   */
  changePassword(
    currentPassword: string,
    newPassword: string,
  ): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>('/auth/security/password/', {
      method: 'POST',
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    })
  },

  /* ---------- Notifications ---------- */

  /**
   * This account's notifications and the unread count.
   *
   * `unread` is passed by the bell's popover so opening it does not require
   * scrolling past a long read history; the count comes back either way
   * because the badge needs the total, not the filtered length.
   */
  listNotifications(unreadOnly = false): Promise<NotificationListResponse> {
    const suffix = unreadOnly ? '?unread=true' : ''
    return request<NotificationListResponse>(`/notifications/${suffix}`)
  },

  /** Mark one read. Resolves to the updated row so the caller can drop the dot. */
  markNotificationRead(id: number): Promise<Notification> {
    return request<Notification>(`/notifications/${id}/read/`, { method: 'POST' })
  },

  /**
   * Mark everything read.
   *
   * Returns the number the server changed rather than assuming the count it
   * sent was accurate: the two tabs case, or a poll that landed mid-request,
   * means the local list and the server can legitimately disagree.
   */
  markAllNotificationsRead(): Promise<{ updated: number }> {
    return request<{ updated: number }>('/notifications/read-all/', { method: 'POST' })
  },

  /** Which notifications this account has opted into. */
  getNotificationPreferences(): Promise<NotificationPreferences> {
    return request<NotificationPreferences>('/notifications/preferences/')
  },

  updateNotificationPreferences(
    patch: Partial<NotificationPreferences>,
  ): Promise<NotificationPreferences> {
    return request<NotificationPreferences>('/notifications/preferences/', {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  },

  /* ---------- AI provider key (bring your own) ---------- */

  /** Whether this account has a key saved. Never returns the key itself. */
  getAiKey(provider = 'gemini'): Promise<AiKeyStatus> {
    return request<AiKeyStatus>(`/auth/ai-key/?provider=${encodeURIComponent(provider)}`)
  },

  /**
   * Store the user's own provider key.
   *
   * The key is sent once and then forgotten by the client: nothing here
   * retains it, and there is no getter that could read it back. Callers
   * should clear their input state as soon as this resolves.
   */
  saveAiKey(apiKey: string, provider = 'gemini'): Promise<AiKeyStatus> {
    return request<AiKeyStatus>('/auth/ai-key/', {
      method: 'POST',
      body: JSON.stringify({ provider, api_key: apiKey }),
    })
  },

  /** Forget the stored key. Idempotent. */
  deleteAiKey(provider = 'gemini'): Promise<AiKeyStatus> {
    return request<AiKeyStatus>(`/auth/ai-key/?provider=${encodeURIComponent(provider)}`, {
      method: 'DELETE',
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
  /**
   * The original uploaded document, through the authenticated API route.
   *
   * The old version linked MEDIA_URL directly and was broken twice: a
   * root-relative `/media/...` was returned unchanged, so the browser
   * resolved it against the *frontend* origin (Vercel) rather than the API
   * (Render), and nothing serves `/media/` in production anyway because
   * Django's `static()` is a no-op unless DEBUG is on.
   *
   * Going through the API also means the file is tenant-scoped, so a resume
   * is not a world-readable asset at a guessable URL.
   */
  resumeFileUrl(resumeId: number): string {
    return `${BASE_URL}/resumes/${resumeId}/file/`
  },

  fileUrl(path: string): string {
    if (/^https?:\/\//i.test(path)) return path
    // Root-relative paths belong to the API, not the frontend. Returning
    // them unchanged silently pointed the browser at the wrong host.
    return `${BASE_URL.replace(/\/api$/, '')}/${path.replace(/^\//, '')}`
  },

  /* ---------- Applications ---------- */

  listApplications(params: { status?: string; job?: number } = {}): Promise<Application[]> {
    const search = new URLSearchParams()
    if (params.status) search.set('status', params.status)
    if (params.job) search.set('job', String(params.job))

    const qs = search.toString()
    return request<Application[]>(`/applications/${qs ? `?${qs}` : ''}`)
  },

  /** Status counts for the tracker header. Scoped server-side to this account. */
  applicationSummary(): Promise<ApplicationSummary> {
    return request<ApplicationSummary>('/applications/?summary=1')
  },

  createApplication(payload: {
    job: number
    tailored_resume?: number | null
  }): Promise<Application> {
    return request<Application>('/applications/', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  getApplication(id: number): Promise<Application> {
    return request<Application>(`/applications/${id}/`)
  },

  updateApplication(
    id: number,
    // `status` was missing here even though the serializer has always
    // accepted it, so the tracker could not move an application along.
    payload: Partial<Pick<Application, 'notes' | 'tailored_resume' | 'status'>>,
  ): Promise<Application> {
    return request<Application>(`/applications/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
  },

  setApplicationStatus(id: number, status: ApplicationStatus): Promise<Application> {
    return request<Application>(`/applications/${id}/status/`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    })
  },

  deleteApplication(id: number): Promise<{ deleted: boolean }> {
    return request<{ deleted: boolean }>(`/applications/${id}/`, { method: 'DELETE' })
  },

  /** Real aggregates for the dashboard. Never hardcoded on the client. */
  dashboardStats(): Promise<DashboardStats> {
    return request<DashboardStats>('/applications/dashboard/')
  },

  /* ---------- AI tailoring ---------- */

  /** Is tailoring available at all? Used to disable the button up front. */
  /**
   * The candidate's chosen qualities, plus the catalogue to choose from.
   *
   * The server owns both the list of valid options and the minimum count, so
   * both are read from here rather than duplicated in the client.
   */
  getQualities(): Promise<QualitiesResponse> {
    return request<QualitiesResponse>('/resumes/qualities/')
  },

  /**
   * Replace the whole selection.
   *
   * PUT rather than PATCH: a partial update would leave the client unable to
   * tell whether the server's stored selection matches what is on screen, and
   * "the minimum of seven" is a property of the selection as a whole.
   */
  saveQualities(qualities: QualitySelection): Promise<QualitiesResponse> {
    return request<QualitiesResponse>('/resumes/qualities/', {
      method: 'PUT',
      body: JSON.stringify({ qualities }),
    })
  },
  tailoringStatus(): Promise<TailoringStatus> {
    return request<TailoringStatus>('/resumes/tailor/status/')
  },

  /**
   * Live progress for the most recent tailoring run.
   *
   * `since` is the `elapsed` cursor from the previous poll, so the server only
   * returns events the caller has not already seen. Omit it for the first
   * call, which returns the whole buffer for this account.
   */
  tailoringProgress(since?: number): Promise<TailoringProgress> {
    const query = since == null ? '' : `?since=${encodeURIComponent(String(since))}`
    return request<TailoringProgress>(`/resumes/tailor/progress/${query}`)
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

  /* ---------- Downloads ---------- */

  /**
   * Download a generated document and hand it to the browser.
   *
   * Returns the filename actually used so the caller can report it. Kept in one
   * place because the Tailor panel and the Resume Workspace both need it, and
   * two copies would eventually disagree about error handling.
   */
  async downloadResume(id: number, format: 'docx' | 'pdf'): Promise<string> {
    // This path does its own fetch rather than going through request(), so it
    // needs the same guard.
    if (API_URL_MISSING) {
      throw new ApiError(API_URL_MISSING_MESSAGE, 0)
    }

    const response = await fetch(`${BASE_URL}/resumes/${id}/download/${format}/`, {
      method: 'GET',
      headers: { Accept: '*/*' },
      credentials: 'include',
    })

    if (!response.ok) {
      let message = `Download failed (${response.status})`
      try {
        message = extractError(await response.json(), message)
      } catch {
        // Non-JSON error body; the status message is enough.
      }
      throw new ApiError(message, response.status)
    }

    const filename = filenameFromDisposition(
      response.headers.get('Content-Disposition'),
      `resume.${format}`,
    )

    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    // Revoking immediately can cancel the download in some browsers, so it is
    // deferred a tick.
    window.setTimeout(() => URL.revokeObjectURL(url), 4000)

    return filename
  },
}

