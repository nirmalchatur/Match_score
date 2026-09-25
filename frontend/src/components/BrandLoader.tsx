import { IconLogo } from './Icons'

/** Branded loading state, reused by the route guards. */
export function BrandLoader({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="boot">
      <span className="boot-mark">
        <IconLogo size={26} />
      </span>
      <span className="boot-label">{label}…</span>
    </div>
  )
}

export default BrandLoader
