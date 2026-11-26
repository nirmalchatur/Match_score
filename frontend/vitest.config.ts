import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * Unit and component tests.
 *
 * Kept separate from vite.config.ts on purpose: that file installs the
 * production `require-api-url` guard and the dev proxy, neither of which a
 * test run should depend on. Tests never touch the network -- `fetch` is
 * stubbed per test -- so no API URL is needed here.
 *
 * Browser-level tests live in `e2e/` and run under Playwright, not here.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    unstubGlobals: true,
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'html', 'lcov'],
      include: ['src/lib/**', 'src/auth/**', 'src/components/**'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**'],
    },
  },
})
