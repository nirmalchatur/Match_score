import type { ReactNode } from 'react'
import type { Toast, ToastVariant } from '../lib/types'
import { IconAlert, IconCheck, IconClose } from './Icons'

const ICONS: Record<ToastVariant, ReactNode> = {
  success: <IconCheck size={17} />,
  error: <IconAlert size={17} />,
  info: <IconAlert size={17} />,
}

export function Toasts({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toast-viewport" role="region" aria-live="polite" aria-label="Notifications">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.variant}`}>
          <span className="toast-icon">{ICONS[toast.variant]}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="toast-title">{toast.title}</div>
            {toast.message ? <div className="toast-msg">{toast.message}</div> : null}
          </div>
          <button
            type="button"
            onClick={() => onDismiss(toast.id)}
            aria-label="Dismiss notification"
            style={{ color: 'var(--text-dim)', display: 'grid', placeItems: 'center' }}
          >
            <IconClose size={15} />
          </button>
        </div>
      ))}
    </div>
  )
}

export default Toasts
