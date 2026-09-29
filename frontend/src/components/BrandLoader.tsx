import { IconLogo } from './Icons'

/**
 * Branded loading state, reused by the route guards.
 *
 * The copy is the point of this component, not the animation. When the session
 * cannot be resolved quickly -- a cold backend, a slow network -- the user is
 * looking at a blank screen with no idea whether anything is happening. Saying
 * what is being waited on, and that the backend may be waking, is the
 * difference between "this is slow" and "this is broken".
 */
export function BrandLoader({
  label = 'Loading',
  hint = 'This only takes a moment on a warm server. A free-tier host that has gone to sleep can take a little longer to start.',
}: {
  label?: string
  hint?: string
}) {
  return (
    <div className="boot">
      <span className="boot-mark">
        <IconLogo size={26} />
      </span>
      <span className="boot-label">{label}…</span>
      <span className="boot-hint">{hint}</span>
    </div>
  )
}

export default BrandLoader
