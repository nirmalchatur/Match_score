import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AtsBadge, AtsMark } from './AtsBadge'

describe('AtsBadge', () => {
  it('names a known board and applies its tone', () => {
    render(<AtsBadge source="Workday" />)
    const badge = screen.getByTitle('Source: Workday')
    expect(badge).toHaveClass('ats-badge', 'ats-workday')
    expect(badge).toHaveTextContent('WWorkday')
  })

  it('degrades to a neutral chip for an unknown or missing source', () => {
    render(<AtsBadge source={null} />)
    const badge = screen.getByTitle('Source: Other board')
    expect(badge).toHaveClass('ats-generic')
  })
})

describe('AtsMark', () => {
  it('keeps the full name reachable via the title', () => {
    render(<AtsMark source="lever" />)
    expect(screen.getByTitle('Source: Lever')).toHaveTextContent('L')
  })
})
