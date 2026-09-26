import { useState } from 'react'
import { ApiError, api } from '../lib/api'

/**
 * Download a saved resume as DOCX or PDF.
 *
 * Shared by the Tailor panel and the Resume Workspace so the loading, error
 * and success behaviour is defined once. Every path clears the busy state —
 * a download that silently hangs would leave the button stuck forever.
 */
export function DownloadButtons({
  resumeId,
  label = 'Download',
  size = 'sm',
}: {
  resumeId: number
  label?: string
  size?: 'sm' | 'md'
}) {
  const [busy, setBusy] = useState<'docx' | 'pdf' | null>(null)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')

  const run = async (format: 'docx' | 'pdf') => {
    setBusy(format)
    setError('')
    setDone('')
    try {
      const filename = await api.downloadResume(resumeId, format)
      setDone(`Downloaded ${filename}`)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'The download could not be completed. Please try again.',
      )
    } finally {
      // Always clears, so the button can never stay stuck loading.
      setBusy(null)
    }
  }

  const cls = size === 'sm' ? 'btn btn-sm' : 'btn'

  return (
    <span className="dl-wrap">
      <button type="button" className={cls} onClick={() => run('docx')} disabled={busy !== null}>
        {busy === 'docx' ? <span className="spinner" /> : null}
        {label} DOCX
      </button>
      <button type="button" className={cls} onClick={() => run('pdf')} disabled={busy !== null}>
        {busy === 'pdf' ? <span className="spinner" /> : null}
        {label} PDF
      </button>

      {done ? <span className="dl-note dl-ok">{done}</span> : null}
      {error ? (
        <span className="dl-note dl-err" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  )
}
