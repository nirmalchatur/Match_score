import { useEffect } from 'react'
import { applySeo } from '../lib/seo'
import type { Seo } from '../lib/seo'

/**
 * Apply a route's title, description and robots tag while it is mounted.
 *
 * Takes the fields rather than the object so callers can pass an inline
 * literal without re-running the effect on every render.
 */
export function usePageMeta({ title, description, path, noindex }: Seo) {
  useEffect(() => {
    applySeo({ title, description, path, noindex })
  }, [title, description, path, noindex])
}
