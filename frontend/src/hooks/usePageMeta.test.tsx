import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SEO, privateSeo } from '../lib/seo'
import { usePageMeta } from './usePageMeta'

function Page({ meta }: { meta: Parameters<typeof usePageMeta>[0] }) {
  usePageMeta(meta)
  return null
}

const robots = () => document.head.querySelector<HTMLMetaElement>('meta[name="robots"]')?.content

describe('usePageMeta', () => {
  it('sets a distinct, indexable title for a public page', () => {
    render(<Page meta={SEO.login} />)
    expect(document.title).toBe('Sign in · TailorUp')
    expect(robots()).toBe('index, follow')
  })

  it('marks signed-in pages noindex and names them in the tab', () => {
    render(<Page meta={privateSeo('Applications', '/app/applications')} />)
    expect(document.title).toBe('Applications · TailorUp')
    expect(robots()).toBe('noindex, nofollow')
  })

  it('updates when the route changes', () => {
    const { rerender } = render(<Page meta={privateSeo('Jobs', '/app/jobs')} />)
    rerender(<Page meta={privateSeo('Settings', '/app/settings')} />)
    expect(document.title).toBe('Settings · TailorUp')
  })
})
