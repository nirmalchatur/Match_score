/**
 * Per-page title, description, canonical and Open Graph tags.
 *
 * This is a client-rendered SPA, so there is no server to render a different
 * `<head>` per route. The defaults in `index.html` are what a crawler sees for
 * any route it does not execute JavaScript for, and this module overrides them
 * once React mounts.
 *
 * The limitation is worth stating rather than hiding: a crawler that does not
 * run JS sees the same title on every URL. This improves sharing previews,
 * the browser tab, and the history entry, which is most of the benefit, but
 * it is not a substitute for server-side rendering if per-route indexing
 * matters later.
 *
 * Every tag is created once and then updated, rather than being replaced
 * wholesale, so a crawler that snapshots the DOM mid-update never sees a
 * half-written head.
 */

export const SITE_NAME = 'TailorUp'
export const SITE_URL =
  (import.meta.env.VITE_SITE_URL as string | undefined) ?? 'https://match-score-delta.vercel.app'

/** ~60 chars is where Google truncates; longer reads as a wall of grey text. */
type Seo = { title: string; description: string; path: string; noindex?: boolean }

/**
 * Find-or-create a meta tag and set its content.
 *
 * Looked up by `attr`+`key` rather than by a selector passed in, so the
 * "does it exist" check and the "create it" path cannot disagree about which
 * element they are talking about.
 */
function setMeta(attr: 'name' | 'property', key: string, value: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.content = value
}

function upsertCanonical(href: string) {
  let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!el) {
    el = document.createElement('link')
    el.rel = 'canonical'
    document.head.appendChild(el)
  }
  el.href = href
}

/**
 * Apply the SEO tags for a route. Safe to call on every render: it only writes
 * when the value differs, so it does not thrash the DOM on re-render.
 */
export function applySeo({ title, description, path, noindex }: Seo) {
  if (typeof document === 'undefined') return

  const fullTitle = path === '/' ? title : `${title} · ${SITE_NAME}`
  const url = `${SITE_URL}${path}`

  if (document.title !== fullTitle) document.title = fullTitle

  setMeta('name', 'description', description)
  setMeta('property', 'og:title', fullTitle)
  setMeta('property', 'og:description', description)
  setMeta('property', 'og:url', url)
  setMeta('name', 'twitter:title', fullTitle)
  setMeta('name', 'twitter:description', description)

  upsertCanonical(url)

  // Authenticated and one-shot pages must never be indexed. They resolve to a
  // login redirect for anyone without a session, and indexing them would
  // advertise URLs with no content behind them.
  setMeta('name', 'robots', noindex ? 'noindex, nofollow' : 'index, follow')
}

export const SEO = {
  home: {
    title: 'TailorUp · Job Matching & Resume Analytics',
    description:
      'Open-source job analysis. Score your master resume against a real posting, see the skill gap, and tailor it. Runs locally with Ollama.',
    path: '/',
  },
  login: { title: 'Sign in', description: 'Sign in to your TailorUp workspace.', path: '/login' },
  signup: {
    title: 'Create your account',
    description: 'Create a TailorUp account and start scoring your resume against real job postings.',
    path: '/signup',
  },
  privacy: {
    title: 'Privacy Policy',
    description: 'What TailorUp stores, what it sends, and what it never sends.',
    path: '/privacy',
  },
  terms: {
    title: 'Terms & Conditions',
    description: 'The terms you agree to by using TailorUp.',
    path: '/terms',
  },
} as const

/** Every route behind a session. `noindex` is set for all of them. */
export const PRIVATE_SEO = { noindex: true } as const
