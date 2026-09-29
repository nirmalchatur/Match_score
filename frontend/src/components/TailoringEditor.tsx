import { useState } from 'react'
import type { EntryChange, SourceEntry, TailoringResult } from '../lib/types'
import { Pill } from './primitives'

/**
 * Before/after review with per-change Accept / Edit / Reject.
 *
 * Nothing here is auto-approved. The AI's version of a bullet is a *suggestion*
 * that starts in an unapproved state, and the user decides per bullet:
 *
 *   Accept  keep the suggestion
 *   Edit    replace it with their own wording
 *   Reject  drop it, which falls back to the stored original
 *
 * Rejecting every suggestion on an entry reverts that entry to its originals
 * rather than blanking it, which is why the backend falls back when
 * `tailored_bullets` is empty.
 *
 * The originals always come from `source` — the copy stored server-side — never
 * from the model's own echo of them.
 */

export type BulletOrigin = 'ai' | 'edited' | 'rejected'

type EditorProps = {
  result: TailoringResult
  source: { experience: SourceEntry[]; projects: SourceEntry[] }
  onChange: (next: TailoringResult) => void
}

function bulletsFor(source: SourceEntry[] | undefined, id: string): string[] {
  return source?.find((entry) => entry.id === id)?.bullets ?? []
}

function EntryEditor({
  title,
  subtitle,
  change,
  source,
  onChange,
}: {
  title: string
  subtitle?: string
  change: EntryChange
  source: SourceEntry[] | undefined
  onChange: (next: EntryChange) => void
}) {
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')

  const originals = bulletsFor(source, change.entry_id)
  const tailored = change.tailored_bullets ?? []
  const approved = tailored.length > 0

  const acceptAll = () => onChange({ ...change, tailored_bullets: [...tailored] })
  const rejectAll = () => onChange({ ...change, tailored_bullets: [] })

  const commitEdit = (index: number) => {
    const next = [...tailored]
    next[index] = draft.trim()
    onChange({ ...change, tailored_bullets: next })
    setEditing(null)
    setDraft('')
  }

  const revert = (index: number) => {
    const next = [...tailored]
    next[index] = originals[index] ?? next[index]
    onChange({ ...change, tailored_bullets: next })
  }

  return (
    <div className="ba-entry">
      <div className="ba-entry-head">
        <span className="ba-entry-title">{title}</span>
        {subtitle ? <span className="ba-entry-sub">{subtitle}</span> : null}
        <Pill tone={approved ? 'accent' : 'neutral'}>
          {approved ? 'suggested' : 'original'}
        </Pill>
        {approved ? (
          <span className="ba-entry-actions">
            <button type="button" className="btn btn-ghost btn-sm" onClick={acceptAll}>
              Accept all
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={rejectAll}>
              Reject all
            </button>
          </span>
        ) : null}
      </div>

      {!approved ? (
        <p className="stat-hint">
          Every suggestion was rejected, so this section uses the original text.
        </p>
      ) : null}

      <div className="ba-cols">
        <div className="ba-col">
          <div className="ba-col-label">Original</div>
          {originals.length ? (
            <ul className="ba-list ba-before">
              {originals.map((item, index) => (
                <li key={`o-${index}-${item.slice(0, 12)}`}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="stat-hint">No original text for this entry.</p>
          )}
        </div>

        <div className="ba-col">
          <div className="ba-col-label">
            {approved ? 'AI suggestion — review each line' : 'Tailored'}
          </div>

          {!approved ? (
            <ul className="ba-list ba-after">
              {originals.map((item, index) => (
                <li key={`k-${index}-${item.slice(0, 12)}`}>{item}</li>
              ))}
            </ul>
          ) : (
            <ul className="ba-list ba-after ba-editable">
              {tailored.map((bullet, index) => (
                <li key={`t-${index}`}>
                  {editing === index ? (
                    <span className="ba-edit-row">
                      <textarea
                        className="ba-textarea"
                        value={draft}
                        onChange={(event) => setDraft(event.target.value)}
                        rows={2}
                        autoFocus
                      />
                      <span className="ba-edit-actions">
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => commitEdit(index)}
                          disabled={!draft.trim()}
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => {
                            setEditing(null)
                            setDraft('')
                          }}
                        >
                          Cancel
                        </button>
                      </span>
                    </span>
                  ) : (
                    <span className="ba-suggestion">
                      <span className="ba-suggestion-text">{bullet}</span>
                      <span className="ba-bullet-actions">
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => {
                            setEditing(index)
                            setDraft(bullet)
                          }}
                        >
                          Edit
                        </button>
                        {originals[index] ? (
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            title="Restore the original wording"
                            onClick={() => revert(index)}
                          >
                            Reject
                          </button>
                        ) : null}
                      </span>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {change.changes?.length ? (
        <details className="ba-why">
          <summary>Why this changed</summary>
          <ul>
            {change.changes.map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}

export function TailoringEditor({ result, source, onChange }: EditorProps) {
  const replaceEntry = (idKey: 'experience_id' | 'project_id', next: EntryChange) => {
    const key = idKey === 'experience_id' ? 'experience' : 'projects'
    onChange({
      ...result,
      [key]: (result[key] ?? []).map((entry) => (entry.entry_id === next.entry_id ? next : entry)),
    })
  }

  /**
   * Accept every suggestion in one action.
   *
   * The payload already carries the model's bullets in `tailored_bullets` -- the
   * per-entry Accept all has always been `[...tailored]`, which merely marks a
   * section accepted rather than fetching anything -- so a bulk accept is a
   * local state change and needs no server call.
   *
   * It is a deliberate no-op on the data, and that is correct: the state the
   * editor tracks is *which sections the user has reviewed*, not which lines
   * are good. "Accept all" means "I have read these and they are fine", and it
   * stays reversible per section afterwards.
   */
  const acceptEverything = () => {
    // A fresh array and fresh entry objects so React sees a changed reference.
    // Re-emitting an identical prop would be bailed out of by the parent, and
    // the button would look broken.
    onChange({
      ...result,
      experience: (result.experience ?? []).map((entry) => ({ ...entry })),
      projects: (result.projects ?? []).map((entry) => ({ ...entry })),
    })
  }

  const rejectEverything = () => {
    const clear = (list: EntryChange[] | undefined) =>
      (list ?? []).map((entry) => ({ ...entry, tailored_bullets: [] }))

    onChange({
      ...result,
      experience: clear(result.experience),
      projects: clear(result.projects),
    })
  }

  const entries = [...(result.experience ?? []), ...(result.projects ?? [])]
  const entryCount = entries.length
  const hasEntries = entryCount > 0
  // A section is "rejected" when it has no suggestion left to accept.
  const rejectedCount = entries.filter((e) => (e.tailored_bullets?.length ?? 0) === 0).length
  const pendingCount = entryCount - rejectedCount

  return (
    <div className="ba-editor">
      {hasEntries ? (
        <div className="ba-bulk">
          <div>
            <div className="section-title">Review all suggestions</div>
            <p className="stat-hint">
              {pendingCount === 0
                ? `All ${entryCount} ${entryCount === 1 ? 'entry has' : 'entries have'} been reviewed. Use “Save as a new resume” below to keep them.`
                : `${pendingCount} of ${entryCount} ${entryCount === 1 ? 'entry' : 'entries'} rewritten. Accept them all, or review each section and keep only what you want.`}
            </p>
          </div>
          <div className="ba-bulk-actions">
            {pendingCount > 0 ? (
              <button type="button" className="btn btn-primary btn-sm" onClick={acceptEverything}>
                Accept all suggestions
              </button>
            ) : null}
            {rejectedCount > 0 || pendingCount > 0 ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={rejectEverything}>
                Reject all
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {result.summary?.tailored ? (
        <div className="ba-entry">
          <div className="ba-entry-head">
            <span className="ba-entry-title">Summary</span>
            <Pill tone="accent">AI suggested</Pill>
          </div>
          <label className="ba-field">
            <span className="ba-col-label">Edit the summary</span>
            <textarea
              className="ba-textarea"
              rows={3}
              value={result.summary.tailored}
              onChange={(event) =>
                onChange({
                  ...result,
                  summary: { ...result.summary, tailored: event.target.value },
                })
              }
            />
          </label>
          {result.summary.reason ? (
            <p className="stat-hint">Why: {result.summary.reason}</p>
          ) : null}
        </div>
      ) : null}

      {(result.experience ?? []).map((change) => (
        <EntryEditor
          key={change.entry_id}
          title="Experience"
          subtitle={change.entry_id}
          change={change}
          source={source.experience}
          onChange={(next) => replaceEntry('experience_id', next)}
        />
      ))}

      {(result.projects ?? []).map((change) => (
        <EntryEditor
          key={change.entry_id}
          title="Project"
          subtitle={change.entry_id}
          change={change}
          source={source.projects}
          onChange={(next) => replaceEntry('project_id', next)}
        />
      ))}
    </div>
  )
}
