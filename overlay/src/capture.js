// Hidden window: microphone (any OS) and Windows system loopback -> 16 kHz mono PCM16, 100 ms frames -> main.
// Same worklet as frontend/src/lib/audio.ts.
const WORKLET = `
class PCM16Capture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]; if (!ch) return true;
    const out = new Int16Array(ch.length);
    for (let i = 0; i < ch.length; i++) { const s = Math.max(-1, Math.min(1, ch[i])); out[i] = s < 0 ? s * 0x8000 : s * 0x7fff; }
    this.port.postMessage(out.buffer, [out.buffer]); return true;
  }
}
registerProcessor('pcm16-capture', PCM16Capture);`
const FRAME_SAMPLES = 1600
let ctx = null
let stream = null

async function start(source) {
  stop()
  stream = source === 'mic'
    ? await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
    : await navigator.mediaDevices.getDisplayMedia({ audio: true, video: true }) // main.mjs answers with loopback audio
  stream.getVideoTracks().forEach((t) => t.stop())
  if (!stream.getAudioTracks().length) throw new Error('no audio track (system audio not available on this OS)')
  ctx = new AudioContext({ sampleRate: 16000 })
  await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' })))
  const node = new AudioWorkletNode(ctx, 'pcm16-capture')
  let buf = []
  let n = 0
  node.port.onmessage = (e) => {
    const a = new Int16Array(e.data)
    buf.push(a); n += a.length
    if (n < FRAME_SAMPLES) return
    const out = new Int16Array(n)
    let o = 0
    for (const b of buf) { out.set(b, o); o += b.length }
    window.kin.pcm(out.buffer)
    buf = []; n = 0
  }
  ctx.createMediaStreamSource(stream).connect(node)
  node.connect(ctx.destination) // worklet output is silent; the connection keeps it pulling
}

function stop() {
  stream?.getTracks().forEach((t) => t.stop())
  ctx?.close()
  stream = null
  ctx = null
}

window.kin.on((m) => {
  if (m.type === 'capture:start') start(m.source).catch((e) => window.kin.captureError(e.message))
  if (m.type === 'capture:stop') stop()
})
