import { formatDate, stepIcon } from '../lib/format'
import type { PipelineStep } from '../lib/types'
import { IconCheck, IconClock } from './Icons'

const FALLBACK: PipelineStep[] = [
  { name: 'URL validated', status: 'complete' },
  { name: 'Job page collected', status: 'complete' },
  { name: 'Job details extracted', status: 'complete' },
  { name: 'JD analyzed', status: 'pending' },
  { name: 'Skills extracted', status: 'pending' },
  { name: 'Resume matched', status: 'pending' },
  { name: 'Match score calculated', status: 'pending' },
]

export function StepList({
  steps,
  updatedAt,
}: {
  steps?: PipelineStep[]
  updatedAt?: string
}) {
  const items = steps && steps.length > 0 ? steps : FALLBACK
  const done = items.filter((step) => stepIcon(step.status) === 'check').length

  return (
    <div>
      <div className="section-title">
        <span>Pipeline</span>
        <span style={{ marginLeft: 'auto', letterSpacing: '0.04em', textTransform: 'none' }}>
          {done}/{items.length} complete
        </span>
      </div>

      <div className="steps">
        {items.map((step, index) => {
          const state = stepIcon(step.status)
          return (
            <div key={`${step.name}-${index}`} className={`step ${state}`}>
              <span className="step-dot">
                {state === 'check' ? (
                  <IconCheck size={10} />
                ) : state === 'spinner' ? (
                  <IconClock size={9} />
                ) : null}
              </span>
              <span className="step-name">{step.name}</span>
              {state !== 'pending' ? (
                <span className="step-tag">{state === 'check' ? 'done' : 'active'}</span>
              ) : null}
            </div>
          )
        })}
      </div>

      {updatedAt ? (
        <div className="stat-hint" style={{ marginTop: 10 }}>
          Last updated {formatDate(updatedAt)}
        </div>
      ) : null}
    </div>
  )
}
