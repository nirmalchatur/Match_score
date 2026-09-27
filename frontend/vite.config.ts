import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

/**
 * Refuse to ship a production bundle that has nowhere to send its API calls.
 *
 * `src/lib/api.ts` falls back to a relative `/api` prefix when
 * `VITE_API_URL` is unset, which is exactly right for `vite dev` (the dev
 * proxy forwards to Django) and exactly wrong in production: the SPA is
 * served by Vercel and Django lives on Render, so every request would go to
 * the Vercel domain. The static site answers those with a bare
 * "405 Method Not Allowed" on signup, and "Request failed (405)" in the UI.
 *
 * That failure is very hard to trace back to a missing environment variable,
 * so it is turned into a build error here instead: the deploy fails loudly,
 * naming the variable, at the moment it can still be fixed.
 */
function requireApiUrl(mode: string, env: Record<string, string>): Plugin {
  return {
    name: 'require-api-url',
    apply: 'build',
    buildStart() {
      // Dev and preview builds keep the relative default on purpose.
      if (mode !== 'production') return

      const url = (env.VITE_API_URL || '').trim()

      if (!url) {
        // Escape hatch for a deliberate same-origin deployment, where a
        // reverse proxy in front of Django serves both the SPA and /api.
        if (env.ALLOW_RELATIVE_API === '1') {
          this.warn(
            'VITE_API_URL is unset and ALLOW_RELATIVE_API=1, so the bundle ' +
              'will call its own origin. This is only correct if /api is ' +
              'proxied to Django on the same host.',
          )
          return
        }

        this.error(
          'VITE_API_URL is not set, so the bundle would call its own origin ' +
            'instead of the Django API.\n' +
            'Set it in Vercel under Project > Settings > Environment Variables, ' +
            'including the trailing /api:\n\n' +
            '  VITE_API_URL=https://<your-render-host>/api\n\n' +
            'Or export it before building. To build a same-origin bundle on ' +
            'purpose, set ALLOW_RELATIVE_API=1.',
        )
      }

      if (!/^https?:\/\//.test(url)) {
        this.error(
          `VITE_API_URL must be an absolute http(s) URL, got "${url}".\n` +
            'A relative value cannot reach the API from the deployed site.',
        )
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // The third argument '' loads every variable, not just the VITE_ prefixed
  // ones, so the guard above sees the same value the client will.
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react(), requireApiUrl(mode, env)],
    server: {
      // Forward API and media traffic to Django so the dev server avoids CORS
      // entirely. Set VITE_API_URL to point the app at a different backend.
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
        // Django's default MEDIA_URL. Harmless if the backend never serves media.
        '/media': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
  }
})
