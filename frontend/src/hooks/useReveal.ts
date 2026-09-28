import { useEffect } from 'react'

/**
 * Scroll-triggered reveal animations.
 *
 * Deliberately NOT a dependency. The whole effect is one observer that adds a
 * class; the actual movement lives in `styles/motion.css`, so motion can be
 * tuned (or removed) without touching React.
 *
 * Three properties matter more than the animation itself:
 *
 * 1. **Progressive enhancement.** The stylesheet only hides `[data-reveal]`
 *    while `<html>` carries `data-reveal-ready`, an attribute set here, in
 *    JavaScript. So if the bundle fails, JS is disabled, or the observer never
 *    runs, the page renders fully visible instead of blank. Motion is the
 *    enhancement; content is the baseline.
 *
 * 2. **Reduced motion is a hard stop.** We check the media query up front and
 *    never even construct the observer. A `prefers-reduced-motion` user gets
 *    zero transitions rather than "shorter" ones.
 *
 * 3. **One-shot.** Elements unobserve as soon as they are revealed, so the
 *    observer stops doing work as the user scrolls back up.
 */
export function useReveal() {
  useEffect(() => {
    if (typeof window === 'undefined') return

    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduced) return

    // No IntersectionObserver (old Safari, jsdom, some test harnesses):
    // leave the page visible. Better plain than blank.
    if (typeof IntersectionObserver === 'undefined') return

    const root = document.documentElement
    const nodes = document.querySelectorAll<HTMLElement>('[data-reveal]')
    if (nodes.length === 0) return

    // JS is running and will actually reveal them, so let the CSS take these
    // elements out of their visible state.
    root.setAttribute('data-reveal-ready', '')

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          entry.target.classList.add('is-revealed')
          observer.unobserve(entry.target)
        }
      },
      {
        // Fire a little before the top edge reaches the viewport bottom, and
        // require a real slice to be visible, so a tall section cannot
        // trigger off a 2px sliver.
        rootMargin: '0px 0px -12% 0px',
        threshold: 0.12,
      },
    )

    nodes.forEach((node) => observer.observe(node))

    return () => {
      observer.disconnect()
      root.removeAttribute('data-reveal-ready')
    }
  }, [])
}
