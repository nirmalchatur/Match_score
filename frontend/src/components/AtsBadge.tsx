import type { ReactNode } from 'react'
import { atsLabel } from '../lib/format'

/**
 * A small badge naming the board a posting came from.
 *
 * Why not the real company logos
 * ------------------------------
 * Greenhouse, Workday, Lever and every other ATS brand their marks, and
 * shipping those as image assets means redistributing trademarked artwork and
 * keeping a binary in the repo per vendor. The initial-letter monogram below
 * carries the same information for a user scanning a list -- which board did
 * this come from -- with none of that.
 *
 * Unknown slugs degrade to a neutral chip rather than disappearing. A job
 * analysed before the source field existed, or from a board added after this
 * build, should still show *something*: "we do not know where this came
 * from" is useful to see once, whereas a missing badge is just a gap.
 */

const BRAND: Record<string, { tone: string }> = {
  greenhouse: { tone: 'ats-greenhouse' },
  workday: { tone: 'ats-workday' },
  lever: { tone: 'ats-lever' },
  ashby: { tone: 'ats-ashby' },
  linkedin: { tone: 'ats-linkedin' },
  indeed: { tone: 'ats-indeed' },
}

const FALLBACK = { tone: 'ats-generic' }

export function AtsBadge({ source }: { source?: string | null }) {
  const key = (source ?? '').trim().toLowerCase()
  const tone = BRAND[key]?.tone ?? FALLBACK.tone
  const label = atsLabel(key)

  return (
    <span className={`ats-badge ${tone}`} title={`Source: ${label}`}>
      <span className="ats-mark" aria-hidden="true">
        {label.charAt(0).toUpperCase()}
      </span>
      <span className="ats-name">{label}</span>
    </span>
  )
}

/**
 * The same information, collapsed to a mark.
 *
 * Used in the dense job list where a full label on every row would compete
 * with the title for attention. The full name stays in the title attribute so
 * it is still reachable on hover and to a screen reader via the row.
 */
export function AtsMark({ source }: { source?: string | null }): ReactNode {
  const key = (source ?? '').trim().toLowerCase()
  const tone = BRAND[key]?.tone ?? FALLBACK.tone
  const label = atsLabel(key)

  return (
    <span className={`ats-mark ats-mark-sm ${tone}`} title={`Source: ${label}`}>
      {label.charAt(0).toUpperCase()}
    </span>
  )
}
