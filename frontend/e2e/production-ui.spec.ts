import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { expect, test } from './fixtures.ts'

/**
 * Guards for the production-readiness pass: accessibility, phone layout, the
 * navigation drawer, and the topbar search. Each test here pins something
 * that was broken before that pass, so a regression fails CI instead of
 * waiting for a user to notice.
 */

const PHONE = { width: 390, height: 844 }
const WCAG = ['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice']

async function horizontalOverflow(page: Page) {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}

test.describe('accessibility (axe, WCAG 2.1 AA)', () => {
  for (const path of ['/', '/login', '/signup', '/privacy', '/terms', '/no-such-page']) {
    for (const [label, viewport] of [
      ['desktop', { width: 1280, height: 800 }],
      ['phone', PHONE],
    ] as const) {
      test(`${path} has no violations on ${label}`, async ({ page, api }) => {
        api.anonymous()
        await page.setViewportSize(viewport)
        await page.goto(path)
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

        const { violations } = await new AxeBuilder({ page }).withTags(WCAG).analyze()
        // Readable failure: rule id and the first offending selector.
        expect(
          violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(' ')}`),
        ).toEqual([])
      })
    }
  }

  test('the signed-in shell has no violations', async ({ page, api }) => {
    api.signedIn()
    await page.goto('/app/dashboard')
    await expect(page.getByRole('main')).toBeVisible()
    const { violations } = await new AxeBuilder({ page }).withTags(WCAG).analyze()
    expect(violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(' ')}`)).toEqual([])
  })
})

test.describe('page titles', () => {
  test('each route names itself, and app pages are noindex', async ({ page, api }) => {
    api.signedIn()
    await page.goto('/app/applications')
    await expect(page).toHaveTitle('Applications · TailorUp')
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, nofollow')
  })
})

test.describe('phone layout', () => {
  test.use({ viewport: PHONE })

  for (const path of ['/', '/login', '/privacy']) {
    test(`${path} does not scroll sideways`, async ({ page, api }) => {
      api.anonymous()
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      expect(await horizontalOverflow(page)).toBe(0)
    })
  }

  test('the app shell does not scroll sideways', async ({ page, api }) => {
    api.signedIn()
    await page.goto('/app/dashboard')
    await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible()
    expect(await horizontalOverflow(page)).toBe(0)
  })

  test('navigation lives in a drawer that opens, traps focus in, and closes', async ({ page, api }) => {
    api.signedIn()
    await page.goto('/app/dashboard')

    const menu = page.getByRole('button', { name: 'Open navigation' })
    const nav = page.getByRole('navigation', { name: 'Main navigation' })
    await expect(menu).toBeVisible()
    await expect(nav).toBeHidden()

    await menu.click()
    await expect(nav).toBeVisible()
    await expect(page.getByRole('button', { name: 'Close navigation' })).toBeFocused()

    await page.keyboard.press('Escape')
    await expect(nav).toBeHidden()
    await expect(menu).toBeFocused()

    // Choosing a destination navigates and closes the drawer.
    await menu.click()
    await nav.getByRole('button', { name: 'Applications' }).click()
    await expect(page).toHaveURL(/\/app\/applications$/)
    await expect(nav).toBeHidden()
  })
})

test.describe('desktop shell', () => {
  test('shows the sidebar and hides the drawer controls', async ({ page, api }) => {
    api.signedIn()
    await page.goto('/app/dashboard')
    await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    // Regression: .btn's display rule once beat the hide rule, so these
    // phone-only buttons showed on desktop.
    await expect(page.getByRole('button', { name: 'Open navigation' })).toBeHidden()
    await expect(page.getByRole('button', { name: 'Close navigation' })).toBeHidden()
  })

  test('the skip link jumps to the main content', async ({ page, api }) => {
    api.signedIn()
    await page.goto('/app/dashboard')
    await page.keyboard.press('Tab')
    const skip = page.getByRole('link', { name: 'Skip to content' })
    await expect(skip).toBeFocused()
    await skip.press('Enter')
    await expect(page.getByRole('main')).toBeFocused()
  })

  test('the topbar search opens Jobs with the query', async ({ page, api }) => {
    // Regression: this box used to store what was typed and do nothing.
    let query: string | null = null
    api.signedIn().on('GET', '/jobs/', (route) => {
      query = new URL(route.request().url()).searchParams.get('q')
      return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })
    await page.goto('/app/dashboard')

    const search = page.getByRole('searchbox', { name: 'Search your jobs…' })
    await search.fill('  stripe  ')
    await search.press('Enter')

    await expect(page).toHaveURL(/\/app\/jobs\?q=stripe$/)
    await expect(page.getByRole('searchbox', { name: 'Search jobs' })).toHaveValue('stripe')
    await expect.poll(() => query).toBe('stripe')
  })
})
