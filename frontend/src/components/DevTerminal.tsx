import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { atsLabel } from '../lib/format'
import { IconTerminal } from './Icons'
import type { Job, TailoringStatus } from '../lib/types'

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

  return (
    <div className="devterm">
      <div className="devterm-head">
        <span className="mono">console</span>
        <button
          type="button"
          className="devterm-x"
          onClick={() => setOpen(false)}
          aria-label="Close console"
        >
          x
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
  )
}

export default DevTerminal
