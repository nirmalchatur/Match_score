import { useCallback, useRef, useState } from 'react'
import type { Toast, ToastVariant } from '../lib/types'

type Input = { variant: ToastVariant; title: string; message?: string }

let nextId = 0

/** Minimal toast queue — no external state library needed. */
export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef<number[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback(
    ({ variant, title, message }: Input) => {
      const id = ++nextId
      setToasts((current) => [...current, { id, variant, title, message }])
      const timer = window.setTimeout(() => dismiss(id), 5200)
      timers.current.push(timer)
      return id
    },
    [dismiss],
  )

  return {
    toasts,
    dismiss,
    notify: {
      success: (title: string, message?: string) => push({ variant: 'success', title, message }),
      error: (title: string, message?: string) => push({ variant: 'error', title, message }),
      info: (title: string, message?: string) => push({ variant: 'info', title, message }),
    },
  }
}
