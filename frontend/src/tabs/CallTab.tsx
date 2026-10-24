import { useEffect, useRef, useState } from 'react'
import { api, wsUrl, type Transcript as T, type Person } from '../lib/api'
import { Mic, Player } from '../lib/audio'
import { Utterance } from './Transcript'

type Role = 'grandparent' | 'grandchild'

export default function CallTab() {
  const [role, setRole] = useState<Role>((localStorage.getItem('kin.role') as Role) || 'grandparent')
  const [callId, setCallId] = useState<string>(localStorage.getItem('kin.call') || '')
  const [people, setPeople] = useState<Person[]>([])
  const [status, setStatus] = useState('idle')
  const [peer, setPeer] = useState(false)
  const [partial, setPartial] = useState('')
  const [utts, setUtts] = useState<T[]>([])
  const [text, setText] = useState('')
  const [micOn, setMicOn] = useState(false)
  const [asrNote, setAsrNote] = useState('')
  const [verified, setVerified] = useState<Record<number, boolean>>({})
  const ws = useRef<WebSocket | null>(null)
  const mic = useRef(new Mic())
  const player = useRef(new Player())
  const names = Object.fromEntries(people.map(p => [p.id, p.name]))
  const person = role === 'grandparent' ? (people.find(p => p.id === 'p_kamala')?.id || people.find(p => !p.is_learner)?.id) : people.find(p => p.is_learner)?.id

  useEffect(() => { api<{ people: Person[] }>('/api/family/graph').then(g => setPeople(g.people)).catch(() => {}) }, [])

  async function newCall() {
    const r = await api<{ id: number }>('/api/calls', { method: 'POST', body: JSON.stringify({}) })
    setCallId(String(r.id)); localStorage.setItem('kin.call', String(r.id))
  }

  function join() {
    if (!callId || !person) return
    localStorage.setItem('kin.role', role)
    player.current.unlock()
    const sock = new WebSocket(wsUrl(`/ws/call/${callId}?role=${role}&person=${person}`))
    sock.binaryType = 'arraybuffer'
    sock.onopen = () => setStatus('connected')
    sock.onclose = () => { setStatus('idle'); setPeer(false); stopMic() }
    sock.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) { player.current.play(e.data); return }
      const m = JSON.parse(e.data)
      switch (m.type) {
        case 'joined': setPeer(m.peer_present); break
        case 'peer': setPeer(m.present); break
        case 'partial': setPartial(m.text); break
        case 'transcript': setPartial(''); setUtts(u => [m as T, ...u].slice(0, 50)); break
        case 'latency': setUtts(u => u.map(x => x.utterance_id === m.utterance_id ? { ...x, latencies: m.latencies } : x)); break
        case 'status': if (m.asr === 'unavailable') setAsrNote(`ASR unavailable (${m.detail}). Typed input still works.`); break
        case 'error': setAsrNote(`${m.stage}: ${m.message}`); break
      }
    }
    ws.current = sock
  }
  function leave() { ws.current?.close(); ws.current = null }
  function say() { if (!text.trim() || !ws.current) return; ws.current.send(JSON.stringify({ type: 'text', text })); setText('') }
  async function startMic() {
    try { await mic.current.start(buf => { if (ws.current?.readyState === 1) ws.current.send(buf) }); setMicOn(true) }
    catch (e) { setAsrNote(`mic: ${String(e)}`) }
  }
  function stopMic() { mic.current.stop(); setMicOn(false) }
  function verify(id: number, ok: boolean) { ws.current?.send(JSON.stringify({ type: 'verify', utterance_id: id, understood: ok })); setVerified(v => ({ ...v, [id]: ok })) }
  const connected = status === 'connected'

  return (
    <>
      <div className="panel">
        <h2>Join a call</h2>
        <div className="row">
          <select value={role} onChange={e => setRole(e.target.value as Role)} disabled={connected}>
            <option value="grandparent">Grandparent (speaks Tamil)</option>
            <option value="grandchild">Grandchild (speaks English, learning)</option>
          </select>
          <input placeholder="call id" value={callId} onChange={e => setCallId(e.target.value)} style={{ width: 90 }} disabled={connected} />
          <button onClick={newCall} disabled={connected}>New call</button>
          {!connected ? <button className="primary" onClick={join} disabled={!callId || !person}>Join as {person || '…'}</button> : <button className="danger" onClick={leave}>Leave</button>}
          {connected && (!micOn ? <button onClick={startMic}>🎙 Start mic</button> : <button onClick={stopMic}>⏹ Stop mic</button>)}
          <span className={`pill ${connected ? 'ok' : ''}`}>{status}</span>
          <span className={`pill ${peer ? 'ok' : 'bad'}`}>{peer ? 'peer in call' : 'waiting for peer'}</span>
        </div>
        {asrNote && <div className="small err" style={{ marginTop: 6 }}>{asrNote}</div>}
        <div className="small muted" style={{ marginTop: 6 }}>Open this page on the second laptop, pick the other role, same call id. Both sides can also type instead of speaking.</div>
      </div>

      <div className="panel">
        <h2>Speak by typing {role === 'grandparent' ? '(Tamil, script or romanized)' : '(English)'}</h2>
        <textarea className="say" value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); say() } }}
          placeholder={role === 'grandparent' ? 'உன் மாமா நேத்து போன் பண்ணான்.' : 'Paatti, I will call you on Sunday.'} disabled={!connected} />
        <div className="row"><button className="primary" onClick={say} disabled={!connected || !text.trim()}>Send</button>
          <span className="small muted">Demo lines: “ரவி நேத்து அடையாறுலேர்ந்து போன் பண்ணான்.” · “ரவி கோவையில புது கடை திறந்திருக்காரு.” · “பொழுதே போகலை.”</span></div>
      </div>

      {partial && <div className="panel"><h2>Hearing…</h2><div className="muted">{partial}</div></div>}

      <div className="panel">
        <h2>Transcript</h2>
        {utts.length === 0 && <div className="muted">Nothing yet. Grounded spans glow gold; hover one to see who it is.</div>}
        {utts.map(t => <Utterance key={t.utterance_id} t={t} names={names} onVerify={role === 'grandchild' ? verify : undefined} verified={t.utterance_id in verified ? verified[t.utterance_id] : null} />)}
      </div>

      <Compare />
    </>
  )
}

function Compare() {
  const [text, setText] = useState('ரவி கோவையில புது கடை திறந்திருக்காரு.')
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  async function run() {
    setBusy(true)
    try { setRes(await api('/api/translate/compare', { method: 'POST', body: JSON.stringify({ text, speaker: 'p_kamala', listener: 'p_arjun' }) })) }
    catch (e) { setRes({ error: String(e) }) } finally { setBusy(false) }
  }
  return (
    <div className="panel">
      <h2>Generic vs grounded (same model)</h2>
      <div className="row"><input style={{ flex: 1, minWidth: 240 }} value={text} onChange={e => setText(e.target.value)} /><button className="primary" onClick={run} disabled={busy}>{busy ? '…' : 'Compare'}</button></div>
      {res && (
        <div className="compare" style={{ marginTop: 10 }}>
          <div className="box"><h3>Generic (no family)</h3><div>{res.generic?.translation || <span className="err">{res.generic?.error || res.error}</span>}</div></div>
          <div className="box"><h3>KIN (family-grounded)</h3><div>{res.grounded?.translation}</div>
            <div className="small" style={{ marginTop: 6 }}>{res.grounded?.grounded_spans?.map((s: any, i: number) => <span key={i} className="pill ok">{s.source} → {s.rendered}</span>)}</div>
            {res.grounded?.error && <div className="small muted">model unavailable; showing linker-only rendering</div>}
          </div>
        </div>
      )}
    </div>
  )
}
