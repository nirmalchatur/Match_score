import type { SkillGap } from '../lib/types'

/**
 * Skill gap for one job, projected server-side from MatchEngine.
 *
 * The wording distinction matters and is enforced by the server: a skill in
 * "missing" is one the *resume does not mention*. It is not evidence the
 * candidate cannot do it, so nothing here says "you lack" or "you don't know".
 */
export function SkillGapPanel({ gap }: { gap?: SkillGap }) {
  // No analysis yet is a distinct state from "matched nothing": conflating them
  // would tell a user they match no requirements when nothing was computed.
  if (!gap || !gap.has_analysis) {
    return (
      <div className="ba-inner">
        <div className="section-title">Skill analysis</div>
        <p className="stat-hint" style={{ marginTop: 6 }}>
          No job analysis available.
        </p>
      </div>
    )
  }

  const empty = !gap.matched.length && !gap.partial.length && !gap.missing.length

  return (
    <div className="ba-inner">
      <div className="section-title">Skill analysis</div>
      <p className="stat-hint" style={{ marginTop: 6, marginBottom: 14 }}>
        {gap.summary}
      </p>

      {empty ? (
        <p className="stat-hint">No skill requirements were extracted from this description.</p>
      ) : (
        <div className="sg-groups">
          {gap.matched.length ? (
            <div className="sg-group">
              <div className="sg-group-label">Found in your resume</div>
              <div className="sg-chips">
                {gap.matched.map((skill) => (
                  <span className="sg-chip sg-chip-ok" key={skill}>
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {gap.partial.length ? (
            <div className="sg-group">
              <div className="sg-group-label">Partial match</div>
              <div className="sg-chips">
                {gap.partial.map((item) => (
                  <span className="sg-chip sg-chip-partial" key={item}>
                    {item}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {gap.missing.length ? (
            <div className="sg-group">
              {/* "Not found in current resume" -- deliberately not "you lack". */}
              <div className="sg-group-label">Not found in current resume</div>
              <div className="sg-chips">
                {gap.missing.map((skill) => (
                  <span className="sg-chip sg-chip-missing" key={skill}>
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
