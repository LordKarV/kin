import { useEffect, useReducer, useState } from 'react'
import { ConnectionState } from 'livekit-client'
import { API_KEY } from './api.ts'
import type { KinCall } from './call.ts'
import type { KinMsg } from './cards.ts'
import { initialGc, passthroughParts, pruneRail, reduceGrandchild } from './cards.ts'
import { CloseIcon, HangUpIcon, MicIcon, SpeakerIcon } from './icons.tsx'
import { inviteLink, langLabel } from './links.ts'
import Rail from './Rail.tsx'

const TICK_MS = 1000
const STATE_LABEL: Record<string, string> = { connected: 'Connected', connecting: 'Connecting', reconnecting: 'Reconnecting', signalReconnecting: 'Reconnecting', disconnected: 'Disconnected' }

interface Props { call: KinCall; familyId: number; peerLabel: string; onEnded: () => void }

const clock = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/**
 * One subscription per screen (KinCall replays messages that arrived before it to the first listener): data messages
 * go to onMsg (a state setter, so stable), snapshot changes re-render. Also ticks once a second; returns the time.
 */
function useCallTick(call: KinCall, onEnded: () => void, onMsg: (m: KinMsg) => void): number {
  const [, force] = useReducer((x: number) => x + 1, 0)
  const [now, setNow] = useState(Date.now())
  useEffect(() => call.on((m) => (m ? onMsg(m) : force())), [call])
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), TICK_MS); return () => clearInterval(t) }, [])
  useEffect(() => { if (call.snap.state === ConnectionState.Disconnected && call.snap.connectedAt) onEnded() })
  return now
}

function Controls({ call }: { call: KinCall }) {
  const muted = call.snap.muted
  return (
    <footer className="controls">
      <button className={`round${muted ? ' on' : ''}`} onClick={() => call.setMuted(!muted)} aria-label={muted ? 'Unmute' : 'Mute'} aria-pressed={muted}>
        <MicIcon off={muted} />
      </button>
      <button className="round danger" onClick={call.hangUp} aria-label="Hang up"><HangUpIcon /></button>
    </footer>
  )
}

function AudioUnlock({ call, label }: { call: KinCall; label?: string }) {
  if (call.snap.canPlayAudio) return null
  return <button className="unlock" onClick={call.unlockAudio}><SpeakerIcon />{label && <span>{label}</span>}</button>
}

function Share({ link }: { link: string }) {
  const [open, setOpen] = useState(true)
  const [copied, setCopied] = useState(false)
  if (!open) return null
  const copy = () => navigator.clipboard.writeText(link).then(() => setCopied(true), () => setCopied(false))
  const share = () => navigator.share({ title: 'KIN call', text: 'Join my KIN call', url: link }).catch(() => {}) // cancel is fine
  return (
    <section className="panel share">
      <div className="kind"><span>Invite them to the call</span><button className="icon" onClick={() => setOpen(false)} aria-label="Close"><CloseIcon /></button></div>
      <input readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Invite link" />
      <div className="actions">
        <button className="pill" onClick={copy}>{copied ? 'Copied' : 'Copy link'}</button>
        {'share' in navigator && <button className="pill primary" onClick={share}>Share</button>}
      </div>
    </section>
  )
}

function GrandchildView({ call, familyId, peerLabel, onEnded }: Props) {
  const [gc, setGc] = useState(initialGc)
  const now = useCallTick(call, onEnded, (m) => setGc((s) => reduceGrandchild(s, m, Date.now())))
  useEffect(() => setGc((s) => { const rail = pruneRail(s.rail, now); return rail === s.rail ? s : { ...s, rail } }), [now])
  const { snap, join } = call
  const peer = snap.peerName
  const line = gc.line
  return (
    <main className="screen call">
      <header className="bar">
        <div className="who-bar">
          <b>{peer || peerLabel || 'Your call'}</b>
          <span className="muted small"><span className={`dot ${snap.state === ConnectionState.Connected ? 'on' : ''}`} />
            {peer ? STATE_LABEL[snap.state] ?? snap.state : `Waiting for ${peerLabel || 'them'}`} {snap.connectedAt ? clock(now - snap.connectedAt) : ''}</span>
        </div>
        <span className="brand">KIN</span>
      </header>
      <AudioUnlock call={call} label="Tap to hear the call" />
      {!peer && join && <Share link={inviteLink(location.host, join.call_id, familyId, API_KEY)} />}
      <section className="captions" aria-live="polite">
        {gc.partial && <p className="partial">{gc.partial}</p>}
        {line ? (
          <>
            <p className="tr">{passthroughParts(line.translation, line.passthrough).map((p, i) => (p.pass ? <mark key={i} className="pass">{p.text}</mark> : <span key={i}>{p.text}</span>))}</p>
            <p className="src">{line.src}</p>
          </>
        ) : !gc.partial && <p className="muted">What {peer || peerLabel || 'they'} say shows up here in English.</p>}
        {gc.status && <p className="status warn">{gc.status}</p>}
      </section>
      <Rail rail={gc.rail} now={now} familyId={familyId} setRail={(f) => setGc((s) => ({ ...s, rail: f(s.rail) }))} />
      <Controls call={call} />
    </main>
  )
}

/** Big and simple: what the grandchild said, in her language. No English beyond icons. */
function GrandparentView({ call, onEnded }: Props) {
  const [line, setLine] = useState('')
  useCallTick(call, onEnded, (m) => { if (m.type === 'transcript' && m.role === 'grandchild' && m.translation) setLine(m.translation) })
  const lang = call.join?.heritage_lang || ''
  const { snap } = call
  return (
    <main className="screen call elder" lang={lang || undefined}>
      <header className="bar">
        <div className="who-bar">
          <b>{snap.peerName || ''}</b>
          <span className="muted"><span className={`dot ${snap.peerName && snap.state === ConnectionState.Connected ? 'on' : ''}`} />{lang && langLabel(lang)}</span>
        </div>
        <span className="brand">KIN</span>
      </header>
      <AudioUnlock call={call} />
      <section className="elder-line" aria-live="polite">{line ? <p>{line}</p> : <span className="listening" aria-hidden="true"><i /><i /><i /></span>}</section>
      <Controls call={call} />
    </main>
  )
}

export default function CallScreen(props: Props) {
  return props.call.join?.role === 'grandparent' ? <GrandparentView {...props} /> : <GrandchildView {...props} />
}
