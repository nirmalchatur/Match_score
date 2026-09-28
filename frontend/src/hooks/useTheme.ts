import { useCallback, useEffect, useState } from 'react'

/**
 * Colour scheme, persisted per browser.
 *
 * Three values rather than two, because "always light" and "always dark" are
 * different promises from "do what my OS does". A user who never picks one
 * follows the system and, if that changes at sunset, the page changes with it
 * without a reload.
 */
export type Theme = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'tailorup.theme'

function readStored(): Theme {
  const raw = window.localStorage.getItem(STORAGE_KEY)
  return raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'system'
}

function systemPrefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

/**
 * The attribute actually written to <html>.
 *
 * `system` resolves to a concrete theme, because CSS cannot express "follow
 * the OS" through a single selector without a second, duplicated block. Writing
 * the resolved value keeps the stylesheet honest and leaves exactly one source
 * of truth.
 */
function resolve(theme: Theme): 'light' | 'dark' {
  if (theme === 'system') return systemPrefersDark() ? 'dark' : 'light'
  return theme
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readStored)

  const setTheme = useCallback((next: Theme) => {
    window.localStorage.setItem(STORAGE_KEY, next)
    setThemeState(next)
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolve(theme))
    document.documentElement.style.colorScheme = resolve(theme)
  }, [theme])

  // While following the system, react to the OS flipping at sunset or when
  // the user changes it in their settings. Once they choose explicitly this
  // listener is a no-op, because `resolve` ignores the media query.
  useEffect(() => {
    if (theme !== 'system') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () =>
      document.documentElement.setAttribute('data-theme', resolve('system'))
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [theme])

  return { theme, setTheme }
}
