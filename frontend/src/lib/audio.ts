// Mic capture → 16 kHz mono PCM16 frames; playback of incoming PCM16 chunks with gapless scheduling.
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

export class Mic {
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private node: AudioWorkletNode | null = null
  async start(onFrame: (pcm: ArrayBuffer) => void) {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } })
    this.ctx = new AudioContext({ sampleRate: 16000 })
    const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }))
    await this.ctx.audioWorklet.addModule(url)
    const src = this.ctx.createMediaStreamSource(this.stream)
    this.node = new AudioWorkletNode(this.ctx, 'pcm16-capture')
    let buf: Int16Array[] = []; let n = 0
    this.node.port.onmessage = (e) => {
      const a = new Int16Array(e.data); buf.push(a); n += a.length
      if (n >= 1600) { // 100 ms frames
        const out = new Int16Array(n); let o = 0; for (const b of buf) { out.set(b, o); o += b.length }
        onFrame(out.buffer); buf = []; n = 0
      }
    }
    src.connect(this.node); this.node.connect(this.ctx.destination)
  }
  stop() { this.node?.disconnect(); this.stream?.getTracks().forEach(t => t.stop()); this.ctx?.close(); this.ctx = null }
  get active() { return !!this.ctx }
}

export class Player {
  private ctx: AudioContext | null = null
  private nextAt = 0
  private ensure() { if (!this.ctx) { this.ctx = new AudioContext({ sampleRate: 16000 }); this.nextAt = 0 } return this.ctx }
  play(pcm: ArrayBuffer) {
    const ctx = this.ensure()
    const i16 = new Int16Array(pcm); const f32 = new Float32Array(i16.length)
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 0x8000
    const buf = ctx.createBuffer(1, f32.length, 16000); buf.copyToChannel(f32, 0)
    const s = ctx.createBufferSource(); s.buffer = buf; s.connect(ctx.destination)
    const t = Math.max(ctx.currentTime + 0.02, this.nextAt); s.start(t); this.nextAt = t + buf.duration
  }
  unlock() { this.ensure().resume() }
}
