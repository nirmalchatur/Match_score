import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * The request layer, exercised against a stubbed fetch.
 *
 * api.ts holds the CSRF token in module state, so every test imports a fresh
 * copy of the module; otherwise a token fetched in one test leaks into the next
 * and the "fetches a token first" assertions pass for the wrong reason.
 */

type Call = { url: string; init: RequestInit }

function json(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** A queued fetch outcome that rejects instead of resolving. */
class Reject {
  readonly reason: unknown
  constructor(reason: unknown) {
    this.reason = reason
  }
}

function stubFetch(...responses: Array<Response | Reject>) {
  const calls: Call[] = []
  const queue = [...responses]
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init })
      const next = queue.shift()
      if (!next) throw new Error(`unexpected fetch: ${url}`)
      // Not `instanceof Error`: jsdom's DOMException does not extend Error.
      if (next instanceof Reject) throw next.reason
      return next
    }),
  )
  return calls
}

async function loadApi() {
  vi.resetModules()
  return import('./api')
}

describe('api request layer', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends GETs with credentials and no CSRF round trip', async () => {
    const calls = stubFetch(json(200, { authenticated: false, user: null }))
    const { api } = await loadApi()

    await expect(api.me()).resolves.toEqual({ authenticated: false, user: null })

    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe('/api/auth/me/')
    expect(calls[0].init.credentials).toBe('include')
    expect((calls[0].init.headers as Record<string, string>)['X-CSRFToken']).toBeUndefined()
  })

  it('fetches a CSRF token before the first unsafe request, then reuses it', async () => {
    const calls = stubFetch(
      json(200, { csrf_token: 'tok-1' }),
      json(200, { user: { id: 1 } }),
      json(200, { user: { id: 1 } }),
    )
    const { api } = await loadApi()

    await api.login('a@example.com', 'pw')
    await api.login('a@example.com', 'pw')

    expect(calls.map((c) => c.url)).toEqual([
      '/api/auth/csrf/',
      '/api/auth/login/',
      '/api/auth/login/',
    ])
    for (const call of calls.slice(1)) {
      const headers = call.init.headers as Record<string, string>
      expect(headers['X-CSRFToken']).toBe('tok-1')
      expect(headers['Content-Type']).toBe('application/json')
    }
  })

  it('refetches a stale token once on 403 and replays the request', async () => {
    const calls = stubFetch(
      json(200, { csrf_token: 'stale' }),
      json(403, { detail: 'CSRF Failed' }),
      json(200, { csrf_token: 'fresh' }),
      json(200, { user: { id: 1 } }),
    )
    const { api } = await loadApi()

    await expect(api.login('a@example.com', 'pw')).resolves.toEqual({ user: { id: 1 } })

    const replay = calls[3].init.headers as Record<string, string>
    expect(replay['X-CSRFToken']).toBe('fresh')
  })

  it('does not retry a second 403: that one is a real refusal', async () => {
    stubFetch(
      json(200, { csrf_token: 'a' }),
      json(403, { detail: 'CSRF Failed' }),
      json(200, { csrf_token: 'b' }),
      json(403, { detail: 'You do not have permission.' }),
    )
    const { api, ApiError, isAuthError } = await loadApi()

    const error = await api.login('a@example.com', 'pw').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as InstanceType<typeof ApiError>).message).toBe('You do not have permission.')
    expect(isAuthError(error)).toBe(true)
  })

  it.each([
    ['detail', { detail: 'Invalid credentials.' }, 'Invalid credentials.'],
    ['error', { error: 'Boom' }, 'Boom'],
    ['non_field_errors', { non_field_errors: ['Pick one.'] }, 'Pick one.'],
    ['a DRF field error', { email: ['Enter a valid email.'] }, 'Enter a valid email.'],
    ['an unhelpful body', { ok: false }, 'Request failed (400)'],
  ])('surfaces %s as the error message', async (_label, body, message) => {
    stubFetch(json(400, body))
    const { api } = await loadApi()
    await expect(api.me()).rejects.toThrow(message)
  })

  it('reports a timeout as a timeout, not as CORS', async () => {
    stubFetch(new Reject(new DOMException('timed out', 'TimeoutError')))
    const { api } = await loadApi()
    await expect(api.me(10)).rejects.toThrow(/did not respond in time/)
  })

  it('explains a network failure and names the URL it tried', async () => {
    stubFetch(new Reject(new TypeError('Failed to fetch')))
    const { api } = await loadApi()
    await expect(api.me()).rejects.toThrow(/Cannot reach the API at \/api/)
  })
})
