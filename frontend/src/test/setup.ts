// Adds DOM matchers such as toBeInTheDocument() and toBeDisabled() to expect().
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
  window.sessionStorage.clear()
})
