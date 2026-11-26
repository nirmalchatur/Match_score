import { expect, test } from './fixtures.ts'

test.describe('public pages', () => {
  test('landing page renders for a signed-out visitor', async ({ page, api }) => {
    api.anonymous()
    await page.goto('/')

    await expect(page.getByRole('heading', { level: 1 })).toContainText('Know how well you fit')
    await expect(page.getByRole('link', { name: /sign in|log in/i }).first()).toBeVisible()
  })

  test('landing page still renders when the API is unreachable', async ({ page }) => {
    // A cold or down backend must not blank the marketing site: the session
    // check fails and the app falls back to "signed out".
    await page.route('**/api/**', (route) => route.abort('connectionrefused'))
    await page.goto('/')

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('unknown routes show the 404 page', async ({ page, api }) => {
    api.anonymous()
    await page.goto('/definitely-not-a-page')

    await expect(page.getByRole('heading', { name: 'This page does not exist' })).toBeVisible()
  })

  test('legal pages are reachable without signing in', async ({ page, api }) => {
    api.anonymous()
    for (const path of ['/privacy', '/terms']) {
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    }
  })
})

test.describe('auth guards', () => {
  test('a signed-out visitor is sent from the workspace to /login', async ({ page, api }) => {
    api.anonymous()
    await page.goto('/app/dashboard')

    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  })

  test('a signed-in user without a master resume is sent to onboarding', async ({ page, api }) => {
    api.json('GET', '/auth/me/', 200, {
      authenticated: true,
      user: { id: 1, email: 'new@example.com', has_master_resume: false },
    })
    await page.goto('/app/dashboard')

    await expect(page).toHaveURL(/\/setup\/resume$/)
  })
})

test.describe('sign in', () => {
  test('shows the server error for bad credentials and sends a CSRF token', async ({
    page,
    api,
  }) => {
    let csrfHeader: string | null = null
    api
      .anonymous()
      .json('GET', '/auth/csrf/', 200, { csrf_token: 'e2e-token' })
      .on('POST', '/auth/login/', (route) => {
        csrfHeader = route.request().headers()['x-csrftoken'] ?? null
        return route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Invalid email or password.' }),
        })
      })

    await page.goto('/login')
    await page.getByLabel('Email').fill('someone@example.com')
    await page.getByLabel('Password').fill('wrong-password')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByText('Invalid email or password.')).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
    expect(csrfHeader).toBe('e2e-token')
  })
})
