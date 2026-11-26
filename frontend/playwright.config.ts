import { defineConfig, devices } from '@playwright/test'
import { E2E_PORT as PORT, FAKE_API } from './e2e/constants.ts'

/**
 * Browser smoke tests against the real production bundle.
 *
 * The app is built with a fake, unroutable API host and served by
 * `vite preview`. Each test intercepts that host with `page.route`, so the
 * suite needs no Django, no database and no network, and runs the same on a
 * laptop as in CI. What it checks is the thing unit tests cannot: that the
 * built bundle boots, routes, and wires the auth guards together.
 *
 * Backend behaviour is covered by the Django suite and the Newman run
 * (`.github/workflows/api-tests.yml`); this suite is not a substitute for
 * either.
 */

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run build && npm run preview -- --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { VITE_API_URL: FAKE_API },
  },
})
