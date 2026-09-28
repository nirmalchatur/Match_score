/**
 * Cookieless analytics plumbing, kept out of the component file.
 *
 * Split from `components/Analytics.tsx` so that file exports only components,
 * which is what makes React Fast Refresh work during development. Mixing a
 * `trackPageView` helper into a module of components is the usual reason the
 * rule trips.
 *
 * Off by default. That is not timidity, it is the point: TailorUp's stated
 * promise is that your resume does not leave your machine, and bolting a
 * tracker onto the site the moment it loads would contradict the thing the
 * README spends paragraphs defending. Analytics nobody asked for are a privacy
 * cost with no offsetting benefit for a project this size.
 *
 * To enable: set VITE_ANALYTICS_DOMAIN to your Plausible domain. Nothing loads
 * when it is unset -- no script tag, no cookie, no banner.
 *
 * Why Plausible and not GA4: it sets no cookie, needs no consent banner to be
 * lawful under the GDPR, stores no personal data, and has no
 * cross-site-tracking surface. A banner advertising a vendor that does not need
 * consent is the worst of both worlds.
 */

export const ANALYTICS_DOMAIN = (
  import.meta.env.VITE_ANALYTICS_DOMAIN as string | undefined
)?.trim()

export const ANALYTICS_ENABLED = Boolean(ANALYTICS_DOMAIN)

export const CONSENT_KEY = 'tailorup.analytics-consent'

export type Consent = 'granted' | 'denied' | null

export const CONSENT_EVENT = 'tailorup:analytics-consent'

/**
 * Read the stored choice.
 *
 * localStorage throws in some private-browsing modes. That must degrade to
 * "not decided" rather than take down a non-essential feature, so the read is
 * guarded.
 */
export function readConsent(): Consent {
  try {
    const raw = window.localStorage.getItem(CONSENT_KEY)
    return raw === 'granted' || raw === 'denied' ? raw : null
  } catch {
    return null
  }
}

export function writeConsent(choice: Exclude<Consent, null>) {
  try {
    window.localStorage.setItem(CONSENT_KEY, choice)
  } catch {
    /* Not fatal: the choice simply will not persist. */
  }
  window.dispatchEvent(new CustomEvent(CONSENT_EVENT))
}

/** Send a page view. No-op unless analytics are enabled *and* accepted. */
export function trackPageView(path: string) {
  if (!ANALYTICS_ENABLED) return
  if (readConsent() !== 'granted') return
  const w = window as unknown as {
    plausible?: (event: string, opts?: { props?: unknown }) => void
  }
  w.plausible?.('pageview', { props: { path } })
}
