/**
 * The API host the e2e bundle is built against.
 *
 * `.invalid` is reserved (RFC 2606), so if interception ever misses a request
 * it fails fast instead of reaching a real server.
 */
export const FAKE_API = 'https://api.e2e.invalid/api'
export const E2E_PORT = 4173
