// KIN call overlay (Electron main process).
//
// The remote speaker's voice reaches this laptop as system audio from Zoom / Meet / FaceTime / WhatsApp desktop.
// We capture that audio, stream it to KIN as the "grandparent" leg of a call, and draw KIN's output as
// always-on-top transparent windows: a caption bar, a card stack, and a small control pill.
//   macOS:   native/syscap (ScreenCaptureKit) -> stdout PCM16 -> here
//   Windows: hidden capture window, getDisplayMedia + Electron audio 'loopback'
//   any OS:  microphone source (laptop speakers into the mic) as the fallback
import { app, BrowserWindow, desktopCapturer, globalShortcut, ipcMain, screen, session } from 'electron'
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { makeChunker } from './lib.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const KIN_URL = (process.env.KIN_URL || 'http://localhost:8000').replace(/\/$/, '')
const KIN_KEY = process.env.KIN_KEY || ''
// Optional: only capture these apps on macOS, e.g. "us.zoom.xos,com.google.Chrome" (keeps notification dings out)
const CAPTURE_APPS = (process.env.KIN_CAPTURE_APPS || '').split(',').map((s) => s.trim()).filter(Boolean)
const FRAME_BYTES = 3200 // 100 ms of 16 kHz mono PCM16
const CAPTION_IDLE_MS = 15000
const FATAL_CLOSE_CODES = new Set([4401, 4404])

const wins = {}
let run = null // { callId, speaker, source } while running
let ws = null
let syscap = null
let captionTimer = null

// ---- windows ---------------------------------------------------------------
function overlayWindow(name, bounds, { focusable = false } = {}) {
  const w = new BrowserWindow({
    ...bounds, show: false, frame: false, transparent: true, resizable: false, hasShadow: false,
    skipTaskbar: true, focusable, backgroundColor: '#00000000',
    webPreferences: { preload: path.join(here, 'preload.cjs') },
  })
  w.setAlwaysOnTop(true, 'screen-saver')
  w.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  // Best effort: hides the overlay from screen share on Windows and older macOS capture paths; ScreenCaptureKit-based
  // sharers on macOS may still see it.
  w.setContentProtection(true)
  // every window lets clicks through to the call; a page turns this off while the pointer is over its panel
  w.setIgnoreMouseEvents(true, { forward: true })
  w.loadFile(path.join(here, `${name}.html`))
  wins[name] = w
  return w
}

function createWindows() {
  const { x, y, width, height } = screen.getPrimaryDisplay().workArea
  const capW = Math.min(980, width - 80)
  overlayWindow('control', { x: x + width - 380, y: y + 16, width: 360, height: 520 }, { focusable: true }).once('ready-to-show', () => wins.control.show())
  overlayWindow('captions', { x: x + Math.round((width - capW) / 2), y: y + height - 210, width: capW, height: 190 })
  overlayWindow('cards', { x: x + 20, y: y + 16, width: 380, height: Math.max(320, height - 260) }, { focusable: true })
  // never shown: it only owns getUserMedia / getDisplayMedia for the mic and Windows loopback sources
  wins.capture = new BrowserWindow({ show: false, webPreferences: { preload: path.join(here, 'preload.cjs'), backgroundThrottling: false } })
  wins.capture.loadFile(path.join(here, 'capture.html'))
}

const send = (name, msg) => wins[name]?.webContents.send('kin:event', msg)
const sendAll = (msg) => ['control', 'captions', 'cards'].forEach((n) => send(n, msg))
const status = (text, level = 'info') => send('control', { type: 'overlay-status', text, level })

function showCaptions() {
  wins.captions?.showInactive() // never steal focus from the call window
  clearTimeout(captionTimer)
  captionTimer = setTimeout(() => wins.captions?.hide(), CAPTION_IDLE_MS)
}

// ---- KIN backend -----------------------------------------------------------
async function api(p, init = {}) {
  const r = await fetch(KIN_URL + p, { ...init, headers: { 'content-type': 'application/json', ...(KIN_KEY ? { 'X-KIN-Key': KIN_KEY } : {}) } })
  if (!r.ok) throw new Error(`${p}: ${r.status} ${(await r.text()).slice(0, 200)}`)
  return r.json()
}

function connect() {
  const u = new URL(`${KIN_URL.replace(/^http/, 'ws')}/ws/call/${run.callId}`)
  u.searchParams.set('role', 'grandparent')
  u.searchParams.set('person', run.speaker)
  if (KIN_KEY) u.searchParams.set('key', KIN_KEY)
  const sock = new WebSocket(u)
  sock.binaryType = 'arraybuffer'
  sock.onopen = () => status(`Listening on call #${run.callId}`, 'ok')
  sock.onmessage = (e) => {
    if (typeof e.data !== 'string') return // TTS audio: never played here, the call already carries their voice
    let msg
    try { msg = JSON.parse(e.data) } catch { return }
    onKin(msg)
  }
  sock.onclose = (e) => {
    if (ws === sock) ws = null
    if (!run) return
    if (FATAL_CLOSE_CODES.has(e.code)) { status(`KIN refused the connection: ${e.reason || e.code}`, 'error'); stop(); return }
    status(`Reconnecting to KIN (${e.code})`, 'warn')
    setTimeout(() => { if (run && !ws) connect() }, 2000)
  }
  ws = sock
}

function onKin(msg) {
  if (msg.type === 'partial' && msg.role === 'grandparent') { send('captions', msg); showCaptions() }
  else if (msg.type === 'transcript') { sendAll(msg); showCaptions() }
  else if (msg.type === 'glance' || msg.type === 'glance_image' || msg.type === 'enrich') sendAll(msg)
  else if (msg.type === 'status' || msg.type === 'error') status(msg.detail || msg.message || msg.asr || 'KIN status', msg.type === 'error' ? 'error' : 'warn')
}

const sendPcm = (buf) => { if (ws?.readyState === WebSocket.OPEN) ws.send(buf) }

// ---- audio capture ---------------------------------------------------------
function syscapPath() {
  const p = app.isPackaged ? path.join(process.resourcesPath, 'syscap') : path.join(here, '..', 'native', 'syscap')
  return existsSync(p) ? p : null
}

function startSyscap() {
  const bin = syscapPath()
  if (!bin) { status('native/syscap is not built: run `npm run build:native`, or switch the source to Microphone', 'error'); return }
  const chunk = makeChunker(FRAME_BYTES, sendPcm)
  const proc = spawn(bin, CAPTURE_APPS, { stdio: ['pipe', 'pipe', 'pipe'] })
  let lastErr = ''
  proc.stdout.on('data', chunk)
  proc.stderr.on('data', (d) => { lastErr = d.toString().trim().split('\n').pop(); console.log(lastErr) })
  proc.on('exit', (code) => {
    if (syscap === proc) syscap = null
    if (run && code) status(`System audio stopped: ${lastErr || `exit ${code}`}. Grant Screen Recording to this app, or use Microphone.`, 'error')
  })
  syscap = proc
}

function startCapture(source) {
  if (source === 'system' && process.platform === 'darwin') startSyscap()
  else send('capture', { type: 'capture:start', source })
}

function stopCapture() {
  syscap?.stdin.end() // syscap exits when stdin closes
  syscap = null
  send('capture', { type: 'capture:stop' })
}

// ---- lifecycle -------------------------------------------------------------
async function start({ speaker, source, callId, familyId }) {
  if (run) stop()
  const id = Number(callId) || (await api('/api/calls', { method: 'POST', body: JSON.stringify({ transport: 'overlay', family_id: Number(familyId) || null }) })).id
  run = { callId: id, speaker, source, familyId }
  sendAll({ type: 'family', familyId })
  connect()
  startCapture(source)
  return { callId: id }
}

function stop() {
  stopCapture()
  const sock = ws
  run = null
  ws = null
  sock?.close(1000)
  status('Stopped')
}

function toggleOverlay() {
  const visible = wins.control?.isVisible()
  for (const n of ['control', 'captions', 'cards']) visible ? wins[n]?.hide() : n === 'control' && wins[n]?.show()
}

ipcMain.handle('kin:start', (_e, opts) => start(opts))
ipcMain.handle('kin:stop', () => stop())
ipcMain.handle('kin:graph', (_e, familyId) => api(`/api/family/graph${familyId ? `?family_id=${Number(familyId)}` : ''}`))
ipcMain.handle('kin:families', () => api('/api/family/all'))
ipcMain.handle('kin:languages', () => api('/api/languages'))
ipcMain.handle('kin:relations', () => api('/api/family/relations'))
ipcMain.handle('kin:suggest', (_e, term, familyId) => api(`/api/family/suggest?term=${encodeURIComponent(term)}&family_id=${Number(familyId)}`))
ipcMain.handle('kin:setup', (_e, body) => api('/api/family/setup', { method: 'POST', body: JSON.stringify(body) }))
ipcMain.handle('kin:add-relative', async (_e, body) => {
  const out = await api('/api/family/relative', { method: 'POST', body: JSON.stringify(body) })
  sendAll({ type: 'family-changed', familyId: body.family_id, person: out })
  return out
})
ipcMain.on('kin:family-selected', (_e, familyId) => sendAll({ type: 'family', familyId }))
ipcMain.on('kin:text', (_e, line) => { if (ws?.readyState === WebSocket.OPEN && line?.trim()) ws.send(JSON.stringify({ type: 'text', text: line.trim() })) })
ipcMain.on('kin:pcm', (_e, buf) => sendPcm(Buffer.from(buf)))
ipcMain.on('kin:capture-error', (_e, msg) => status(`Audio capture failed: ${msg}`, 'error'))
ipcMain.on('kin:mouse', (e, inside) => BrowserWindow.fromWebContents(e.sender)?.setIgnoreMouseEvents(!inside, { forward: true }))
ipcMain.on('kin:cards', (_e, count) => (count ? wins.cards?.showInactive() : wins.cards?.hide()))
ipcMain.on('kin:quit', () => app.quit())

// a second copy would double every caption and open a second capture stream
if (!app.requestSingleInstanceLock()) app.quit()
app.on('second-instance', () => wins.control?.show())

app.whenReady().then(() => {
  if (process.platform === 'win32') {
    // Windows: system audio comes from Electron's loopback device; the video track is dropped in capture.html
    session.defaultSession.setDisplayMediaRequestHandler((_req, cb) => {
      desktopCapturer.getSources({ types: ['screen'] }).then((s) => cb({ video: s[0], audio: 'loopback' })).catch(() => cb(null))
    })
  }
  app.dock?.hide() // overlay utility, not a dock app (quit from the control pill or the shortcut)
  createWindows()
  globalShortcut.register('CommandOrControl+Shift+K', toggleOverlay)
})

app.on('will-quit', () => { stop(); globalShortcut.unregisterAll() })
app.on('window-all-closed', () => app.quit())
