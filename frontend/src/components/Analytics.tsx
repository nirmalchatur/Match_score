import { useEffect, useState } from 'react'
import {
  ANALYTICS_DOMAIN,
  ANALYTICS_ENABLED,
  CONSENT_EVENT,
  readConsent,
  writeConsent,
  type Consent,
} from '../lib/analytics'

/**
 * Cookieless analytics, and the consent banner that goes with it.
 *
 * The logic lives in `lib/analytics.ts`; this file is components only, which
 * keeps React Fast Refresh working.
 *
 * Neither of these renders anything unless VITE_ANALYTICS_DOMAIN is set. The
 * session and CSRF cookies the app genuinely requires are not presented as a
 * consent choice, because they are not one.
 */
export function Analytics() {
  if (!ANALYTICS_ENABLED) return null
  return (
    <script
      defer
      data-domain={ANALYTICS_DOMAIN}
      src="https://plausible.io/js/script.js"
      // Plausible is a third-party script on a page that may carry a
      // signed-in session. Refusing cross-origin credentials means it cannot
      // read cookies from this origin.
      crossOrigin="anonymous"
    />
  )
}

export function CookieBanner() {
  // Read during the initialiser rather than in an effect: the value is
  // synchronous, and setting state from an effect would render the banner once
  // with null and then again with the stored answer.
  const [choice, setChoice] = useState<Consent>(() =>
    ANALYTICS_ENABLED ? readConsent() : null,
  )

  useEffect(() => {
    // Keeps the banner in sync with a decision made in another tab.
    const onChange = () => setChoice(readConsent())
    window.addEventListener(CONSENT_EVENT, onChange)
    return () => window.removeEventListener(CONSENT_EVENT, onChange)
  }, [])

  if (!ANALYTICS_ENABLED || choice !== null) return null

  const decide = (next: Exclude<Consent, null>) => {
    writeConsent(next)
    setChoice(next)
  }

  return (
    <div className="cookie-banner" role="region" aria-label="Cookie notice">
      <p className="cookie-text">
        This site can count page views with{' '}
        <a href="https://plausible.io" target="_blank" rel="noreferrer">
          Plausible
        </a>
        , which sets no cookies and stores no personal data. It is off unless
        you say yes. See the <a href="/privacy">Privacy Policy</a>.
      </p>
      <div className="cookie-actions">
        <button type="button" className="btn btn-ghost" onClick={() => decide('denied')}>
          No thanks
        </button>
        <button type="button" className="btn btn-primary" onClick={() => decide('granted')}>
          Allow
        </button>
      </div>
    </div>
  )
}
