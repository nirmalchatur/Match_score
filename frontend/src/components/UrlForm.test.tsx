import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { UrlForm } from './UrlForm'

function setup(busy = false) {
  const onSubmit = vi.fn()
  const user = userEvent.setup()
  render(<UrlForm onSubmit={onSubmit} busy={busy} />)
  const input = screen.getByRole('textbox', { name: 'Job posting URL' })
  return { onSubmit, user, input }
}

describe('UrlForm', () => {
  it('submits a trimmed http(s) URL', async () => {
    const { onSubmit, user, input } = setup()

    await user.type(input, '  https://boards.greenhouse.io/acme/jobs/1  ')
    await user.click(screen.getByRole('button', { name: /analyze job/i }))

    expect(onSubmit).toHaveBeenCalledExactlyOnceWith('https://boards.greenhouse.io/acme/jobs/1')
  })

  it('rejects a non-URL without calling the network', async () => {
    const { onSubmit, user, input } = setup()

    await user.type(input, 'not a url{Enter}')

    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText('Enter a full http(s) URL.')).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription('Enter a full http(s) URL.')
  })

  it('rejects non-http schemes', async () => {
    const { onSubmit, user, input } = setup()
    await user.type(input, 'javascript:alert(1){Enter}')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('locks the form while a request is in flight', () => {
    const { input } = setup(true)
    expect(input).toBeDisabled()
    expect(screen.getByRole('button', { name: /analyzing/i })).toBeDisabled()
  })
})
