import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { atsLabel } from '../lib/format'
import { IconTerminal, IconClose } from './Icons'
import type { Job, TailoringStatus } from '../lib/types'
import { createPortal } from 'react-dom'

/**
 * A developer console for the workspace.
 *
 * Not a fake shell: every command below is answered from data the app already
 * has or from endpoints that exist, and the prompt reports what it actually
 * did. A terminal that pretends to run commands teaches the wrong thing about
 * the system it is supposed to be inspecting.
 *
 * Deliberately client-side. Anything that needed a server would be a
 * diagnostic surface reachable from a browser, which is exactly the kind of
 * thing that should not exist without a real authz story.
 *
 * Commands
 *   help              this list
 *   status            provider, model, and whether a key is stored
 *   jobs              recent jobs with match scores
 *   sources           the ATS boards in the registry
 *   quality [n]       your saved qualities, or the catalogue
 *   env               frontend build configuration
 *   clear             clear the buffer
 */
type Line = { text: string; tone?: 'ok' | 'err' | 'dim' }

const BANNER = [
  'TailorUp console -- type `help` for commands',
  'Read-only diagnostics. Nothing here changes stored data.',
]

/** How often to ask the server for progress. Two seconds is responsive enough
 *  to feel live and slow enough not to matter on the API budget. */
const POLL_MS = 2000

/** mm:ss, or h:mm:ss past an hour. A run is long enough to need the hour. */
function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => n.toString().padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

export function DevTerminal({ jobs = [] }: { jobs?: Job[] }) {
  const [open, setOpen] = useState(false)
  const [lines, setLines] = useState<Line[]>(BANNER.map((text) => ({ text, tone: 'dim' })))
  const [input, setInput] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [lines])

  const print = useCallback((text: string | string[], tone: Line['tone'] = 'ok') => {
    setLines((current) =>
      current.concat(
        (Array.isArray(text) ? text : [text]).map((line) => ({ text: line, tone })),
      ),
    )
  }, [])

  const runStatus = useCallback(async () => {
    try {
      const [status, key] = await Promise.all([
        api.tailoringStatus() as Promise<TailoringStatus>,
        api.getAiKey(),
      ])
      print([
        `provider      ${status.provider ?? '(none configured)'}`,
        `model         ${status.model ?? '-'}`,
        `available     ${status.available ? 'yes' : 'no'}`,
        `user key      ${key.configured ? `saved (${key.key_hint})` : 'not set'}`,
        `registered    ${(status.registered ?? []).join(', ') || '-'}`,
      ])
    } catch {
      print('could not reach the API', 'err')
    }
  }, [print])

  const runQuality = useCallback(
    async (n: number) => {
      try {
        const data = await api.getQualities()
        if (n > 0) {
          const kind = data.kinds[n - 1]
          if (!kind) {
            print(`no group ${n}; try 1-${data.kinds.length}`, 'err')
            return
          }
          print([`${data.labels[kind]} (${data.catalogue[kind].length})`, ...data.catalogue[kind]])
          return
        }
        const flat = data.kinds.flatMap((k) => data.qualities[k] ?? [])
        print([
          `selected      ${data.selected_count} of ${data.minimum_total} minimum`,
          ...(flat.length ? flat.map((v) => `  - ${v}`) : ['  (none saved)']),
        ])
      } catch {
        print('could not read qualities', 'err')
      }
    },
    [print],
  )

  const submit = useCallback(
    async (raw: string) => {
      const line = raw.trim()
      if (!line) return
      setHistory((h) => [line, ...h])
      print(`> ${line}`, 'dim')

      const [cmd, ...args] = line.split(/\s+/)
      switch (cmd.toLowerCase()) {
        case 'help':
          print([
            'help              this list',
            'status            provider, model, key',
            'jobs              recent jobs and match scores',
            'sources           ATS boards in the registry',
            'quality [n]       your qualities, or catalogue group n',
            'env               frontend build configuration',
            'clear             clear the buffer',
          ])
          break
        case 'status':
          await runStatus()
          break
        case 'jobs':
          if (!jobs.length) print('no jobs analysed yet', 'dim')
          else
            print(
              jobs
                .slice(0, 12)
                .map(
                  (job) =>
                    `#${String(job.id).padEnd(4)} ${(job.match_score ?? 0).toString().padStart(3)}%  ${atsLabel(job.source).padEnd(10)} ${job.title.slice(0, 42)}`,
                ),
            )
          break
        case 'sources':
          print([
            'greenhouse  *.greenhouse.io, job-boards.greenhouse.io',
            'workday     *.wd[N].myworkdayjobs.com',
            'generic     anything else, via JSON-LD then HTML',
          ])
          break
        case 'quality':
          await runQuality(Number(args[0] ?? 0))
          break
        case 'env':
          print([
            `api base    ${(import.meta.env.VITE_API_URL as string) ?? '(default /api)'}`,
            `build mode  ${import.meta.env.MODE}`,
          ])
          break
        case 'clear':
          setLines([])
          break
        default:
          print(`unknown command: ${cmd}. Try \`help\`.`, 'err')
      }
    },
    [jobs, print, runQuality, runStatus],
  )

  /**
   * Live tailoring progress.
   *
   * Polls only while the console is open, so a closed console costs nothing,
   * and stops as soon as the run reports a terminal state. A CPU run lasts
   * minutes, so the alternative -- nothing on screen until it finishes -- is
   * indistinguishable from a hang.
   *
   * Polling rather than a stream because the run holds a server worker for
   * minutes either way; a long-lived connection would pin one worker per
   * concurrent user for the duration.
   */
  useEffect(() => {
    if (!open) return

    let stopped = false
    let timer = 0
    let cursor: number | undefined
    // The `since` cursor is inclusive, so the last event comes back on every
    // poll. Tracking what has been shown keeps the final line from repeating.
    const seen = new Set<string>()

    const tick = async () => {
      if (stopped) return
      try {
        const data = await api.tailoringProgress(cursor)
        cursor = data.elapsed
        for (const event of data.events) {
          const key = `${event.elapsed}:${event.phase}`
          if (seen.has(key)) continue
          seen.add(key)
          print(
            `[${formatElapsed(event.elapsed)}] ${event.message}`,
            event.level === 'error' ? 'err' : event.level === 'done' ? 'ok' : 'dim',
          )
        }
        // A run that has emitted anything and is no longer active has ended,
        // whether it finished or failed. Stop polling either way.
        if (data.events.length && !data.active) {
          stopped = true
          return
        }
      } catch {
        // A failed poll is not worth reporting every couple of seconds. The
        // run itself surfaces its own error where it matters.
      }
      if (!stopped) timer = window.setTimeout(tick, POLL_MS)
    }

    timer = window.setTimeout(tick, 0)
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [open, print])

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    // Up/Down walk the history in reverse of how it is stored, which is
    // newest-first for convenience.
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      const next = history[0]
      if (next) setInput(next)
      return
    }
    if (event.key === 'Escape') {
      setOpen(false)
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const value = input
      setInput('')
      void submit(value)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        className="nav-item devterm-toggle"
        onClick={() => setOpen(true)}
        title="Developer console"
      >
        <IconTerminal size={17} />
        <span>Dev console</span>
      </button>
    )
  }

  // Rendered through a portal so it is never constrained by the sidebar's
  // 232px column. A terminal needs horizontal room to be readable; inline in
  // the nav it wrapped after about twenty characters, which read as broken
  // rather than merely small.
  return createPortal(
    <div
      className="devterm-scrim"
      role="dialog"
      aria-modal="true"
      aria-label="Developer console"
      onClick={(event) => {
        if (event.target === event.currentTarget) setOpen(false)
      }}
    >
      <div className="devterm">
        <div className="devterm-head">
          <span className="mono">console</span>
          <button
            type="button"
            className="devterm-x"
            onClick={() => setOpen(false)}
            aria-label="Close console"
          >
            <IconClose size={14} />
          </button>
        </div>

        <div className="devterm-out" role="log" aria-live="polite">
          {lines.map((line, index) => (
            <div key={index} className={`devterm-line tone-${line.tone ?? 'ok'}`}>
              {line.text || ' '}
            </div>
          ))}
          <div ref={endRef} />
        </div>

        <div className="devterm-prompt">
          <span className="mono">&gt;</span>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            aria-label="Console command"
            spellCheck={false}
            autoComplete="off"
            placeholder="help"
          />
        </div>
      </div>
    </div>,
    document.body,
  )
}

export default DevTerminal
