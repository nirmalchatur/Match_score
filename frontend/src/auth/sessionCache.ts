import type { User } from '../lib/types'

/**
 * A last-known-good session, mirrored into sessionStorage.
 *
 * Why this exists
 * ---------------
 * The session cookie is HttpOnly, so the browser cannot read it and the SPA
 * has no way to know it is signed in without asking the server. That made
 * `/api/auth/me/` a hard gate on first paint: every route, including the
 * public landing page, rendered the "Restoring your session" loader for the
 * full round trip. On a cold Render free-tier instance that is routinely tens
 * of seconds, during which the user sees a blank screen and cannot even read
 * the marketing page.
 *
 * The fix is to stop treating the server as the *first* source of knowledge
 * rather than the only one. This module holds a short-lived cache of the last
 * confirmed answer so the app can render the right thing immediately and then
 * reconcile in the background.
 *
 * What this is NOT
 * ----------------
 * It is a **render hint, never an authority**. Nothing here can grant access:
 * every protected route still calls the server, and a cache that says
 * "authenticated" against a session the server has since dropped produces a
 * single 401 and a redirect to /login, not a data leak. The reverse -- showing
 * the app shell to someone whose cookie merely *looks* valid -- costs one
 * visible error at worst, which is why the hint is allowed to be optimistic
 * about the user but never about permission.
 *
 * sessionStorage, not localStorage, on purpose: the cache dies with the tab,
 * so closing a tab on a shared machine cannot leave a stale "signed in" behind,
 * and it is not shared across tabs where one user's state could be read by
 * another profile's page.
 */

/** Key namespaced to the app so it cannot collide on a shared origin. */
const STORAGE_KEY = 'tailorup.session-cache'

/**
 * How long a cached answer is trusted for first paint.
 *
 * Short enough that a revoked session does not leave a stale shell sitting on
 * screen for long, long enough to cover a page refresh or a back-navigation --
 * which is the entire case this exists for.
 */
const MAX_AGE_MS = 15 * 60 * 1000

type CachedSession = {
  status: 'authenticated' | 'anonymous'
  user: User | null
  cachedAt: number
}

/**
 * Read the cached session, or null when there is nothing usable.
 *
 * Every failure mode -- storage disabled by a privacy extension, corrupt JSON,
 * an expired entry, a shape from an older build -- returns null rather than
 * throwing. A cache is an optimisation; it must never be able to break boot.
 */
export function readSessionCache(): CachedSession | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null

    const parsed = JSON.parse(raw) as Partial<CachedSession>

    // Validate rather than trust: the value round-tripped through storage
    // that another script, or an older version of this app, may have written.
    if (typeof parsed?.cachedAt !== 'number') return null
    if (parsed.status !== 'authenticated' && parsed.status !== 'anonymous') return null
    if (Date.now() - parsed.cachedAt > MAX_AGE_MS) return null

    return {
      status: parsed.status,
      user: parsed.user ?? null,
      cachedAt: parsed.cachedAt,
    }
  } catch {
    return null
  }
}

/** Record a confirmed session so the next load can paint from it. */
export function writeSessionCache(status: CachedSession['status'], user: User | null): void {
  try {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ status, user, cachedAt: Date.now() }),
    )
  } catch {
    // A full quota or a blocked storage API must not break the sign-in that
    // just succeeded. The cache is optional; the session is not.
  }
}

/** Forget the cached session. Called on sign-out and on an expired session. */
export function clearSessionCache(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // See writeSessionCache: nothing to do, and nothing to report.
  }
}