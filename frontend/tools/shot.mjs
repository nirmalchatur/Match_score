/**
 * Screenshot + layout audit via the Chrome DevTools Protocol.
 *
 * Plain `--window-size` is unreliable on Windows (Chrome clamps the
 * window to a minimum width), which produced a mobile screenshot that
 * was cropped rather than responsive. Device emulation via CDP gives a
 * true 414px viewport.
 *
 *   node tools/shot.mjs <url> <out.png> <width> <height> [dpr]
 */
import { spawn } from 'node:child_process'
import { writeFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const [, , url, out, w = '1440', h = '900', dpr = '1'] = process.argv

const profile = mkdtempSync(join(tmpdir(), 'cdp-shot-'))
const port = 9222 + Math.floor(Math.random() * 400)

const chrome = spawn(CHROME, [
  '--headless=new',
  '--disable-gpu',
  '--hide-scrollbars',
  '--no-first-run',
  '--remote-debugging-port=' + port,
  '--user-data-dir=' + profile,
  'about:blank',
])

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function targetWs() {
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/list`)
      const list = await res.json()
      const page = list.find((t) => t.type === 'page')
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl
    } catch {
      /* chrome not up yet */
    }
    await sleep(250)
  }
  throw new Error('Chrome did not expose a debugging target')
}

const ws = new WebSocket(await targetWs())
await new Promise((r) => (ws.onopen = r))

let id = 0
const pending = new Map()
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data)
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id)
    pending.delete(msg.id)
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
  }
}

const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const n = ++id
    pending.set(n, { resolve, reject })
    ws.send(JSON.stringify({ id: n, method, params }))
  })

await send('Page.enable')
await send('Emulation.setDeviceMetricsOverride', {
  width: Number(w),
  height: Number(h),
  deviceScaleFactor: Number(dpr),
  mobile: Number(w) < 700,
})
await send('Page.navigate', { url })
await sleep(2500)

// Measure real layout overflow rather than eyeballing the PNG.
const { result } = await send('Runtime.evaluate', {
  returnByValue: true,
  expression: `(() => {
    const de = document.documentElement;
    const wide = [...document.querySelectorAll('body *')]
      .filter((el) => el.getBoundingClientRect().right > de.clientWidth + 1)
      .slice(0, 8)
      .map((el) => el.className || el.tagName);
    return JSON.stringify({
      clientWidth: de.clientWidth,
      scrollWidth: de.scrollWidth,
      overflowX: de.scrollWidth > de.clientWidth,
      offenders: wide,
    });
  })()`,
})
console.log(result.value)

const shot = await send('Page.captureScreenshot', {
  format: 'png',
  captureBeyondViewport: true,
})
writeFileSync(out, Buffer.from(shot.data, 'base64'))

ws.close()
chrome.kill()
process.exit(0)
