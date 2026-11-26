import { test as base, expect, type Page, type Route } from '@playwright/test'
import { FAKE_API } from './constants.ts'

type Handler = (route: Route) => Promise<void> | void

/**
 * A tiny fake of the Django API, keyed by path under /api.
 *
 * Anything not registered answers 404 and is recorded in `unhandled`, so a test
 * that triggers an unexpected call can assert on it instead of hanging on a
 * request that never resolves.
 */
export class FakeApi {
  private readonly handlers = new Map<string, Handler>()
  readonly unhandled: string[] = []
  private readonly page: Page

  constructor(page: Page) {
    this.page = page
  }

  on(method: string, path: string, handler: Handler): this {
    this.handlers.set(`${method.toUpperCase()} ${path}`, handler)
    return this
  }

  json(method: string, path: string, status: number, body: unknown): this {
    return this.on(method, path, (route) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) }),
    )
  }

  /** The signed-out answer to the boot-time session check. */
  anonymous(): this {
    return this.json('GET', '/auth/me/', 200, { authenticated: false, user: null })
  }

  async install(): Promise<void> {
    await this.page.route(`${FAKE_API}/**`, async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname.replace(/^\/api/, '')
      const key = `${request.method()} ${path}`
      const handler = this.handlers.get(key)
      if (handler) return handler(route)
      this.unhandled.push(key)
      return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    })
  }
}

export const test = base.extend<{ api: FakeApi }>({
  // Playwright calls this argument `use` in its docs. It is named `provide`
  // here because oxlint's rules-of-hooks reads any `use(...)` call as a React
  // hook and fails the lint job.
  api: async ({ page }, provide) => {
    const api = new FakeApi(page)
    await api.install()
    await provide(api)
  },
})

export { expect }
