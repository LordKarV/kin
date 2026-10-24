import { useEffect, useState } from 'react'
import { api, kinKey } from '../lib/api'

type Summary = { n: number; stages: Record<string, { p50: number; p95: number }>; budget: Record<string, number> }

/** Live p50/p95 per stage vs the plan's budget. */
export function LatencyPanel() {
  const [s, setS] = useState<Summary | null>(null)
  useEffect(() => {
    const tick = () => api<Summary>('/api/latency/summary').then(setS).catch(() => {})
    tick(); const id = setInterval(tick, 4000); return () => clearInterval(id)
  }, [])
  if (!s || !s.n) return <div className="panel"><h2>Latency</h2><div className="muted small">No utterances yet.</div></div>
  const rows: [string, string, number | undefined][] = [['ASR final', 'asr_ms', s.budget.asr_ms], ['Link', 'link_ms', undefined], ['MT', 'mt_ms', s.budget.mt_ms], ['TTS first byte', 'tts_first_byte_ms', s.budget.tts_first_byte_ms], ['Total', 'total_ms', s.budget.total_p50_ms]]
  return (
    <div className="panel">
      <h2>Latency · last {s.n} utterances</h2>
      <table className="small" style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead><tr className="muted"><th align="left">stage</th><th align="right">p50</th><th align="right">p95</th><th align="right">budget</th></tr></thead>
        <tbody>{rows.map(([label, k, b]) => {
          const st = s.stages[k] || { p50: 0, p95: 0 }
          const over = b != null && st.p50 > b
          return <tr key={k}><td>{label}</td><td align="right" className={over ? 'err' : ''}>{st.p50.toFixed(0)} ms</td><td align="right">{st.p95.toFixed(0)} ms</td><td align="right" className="muted">{b != null ? `≤ ${b} ms` : '—'}</td></tr>
        })}</tbody>
      </table>
    </div>
  )
}

type Ended = { summary: string; extracted: any; approved: boolean; error?: string | null }

/** Post-call memory: end → summary + extraction → remember-this → approve. Also a memory search box (what the Muse connector sees). */
export function MemoryPanel({ callId }: { callId: string }) {
  const [res, setRes] = useState<Ended | null>(null)
  const [remember, setRemember] = useState<string[]>([])
  const [approved, setApproved] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [q, setQ] = useState('knee')
  const [hits, setHits] = useState<any[] | null>(null)
  const key = kinKey() || 'change-me'  // dev default; set localStorage kin.key when KIN_API_KEY is real

  async function end() { setBusy(true); try { setRes(await api<Ended>(`/api/calls/${callId}/end`, { method: 'POST' })); setApproved(null) } finally { setBusy(false) } }
  async function approve() { setBusy(true); try { setApproved(await api(`/api/calls/${callId}/approve`, { method: 'POST', body: JSON.stringify({ remember_topics: remember }) })) } finally { setBusy(false) } }
  async function search() { const r = await api<{ results: any[] }>(`/api/v1/memory/search?q=${encodeURIComponent(q)}`, { headers: { 'X-KIN-Key': key, 'content-type': 'application/json' } }); setHits(r.results) }
  const x = res?.extracted || {}
  const items = [...(x.people || []).map((p: any) => `👤 ${p.name} (${p.how_referred}, ${p.inferred_relation})`), ...(x.dishes || []).map((d: any) => `🍲 ${d.name}: ${d.note}`), ...(x.places || []).map((d: any) => `📍 ${d.name}: ${d.note}`), ...(x.events || []).map((e: any) => `📅 ${e.name} (${e.when})`)]
  return (
    <div className="panel">
      <h2>Memory · after the call</h2>
      <div className="row"><button onClick={end} disabled={!callId || busy}>End call &amp; summarize</button><span className="small muted">Summary + extraction via Muse Spark. Health/money/conflict are kept as a topic word unless you choose to remember them.</span></div>
      {res && (
        <div style={{ marginTop: 8 }}>
          <div className="utt"><div className="who"><span>Summary</span>{res.error && <span className="err">{res.error}</span>}</div><div>{res.summary || <span className="muted">(model unavailable)</span>}</div></div>
          {items.length > 0 && <div className="utt"><div className="who"><span>New for the family graph (added on approve)</span></div>{items.map((t, i) => <div key={i}>{t}</div>)}</div>}
          {(x.topics || []).length > 0 && <div className="utt"><div className="who"><span>Sensitive topics · remember this?</span></div>
            {(x.topics || []).map((t: any) => <label key={t.topic} style={{ display: 'block' }}><input type="checkbox" checked={remember.includes(t.topic)} onChange={e => setRemember(r => e.target.checked ? [...r, t.topic] : r.filter(z => z !== t.topic))} /> {t.topic} <span className="muted small">({t.kind}{t.sensitive ? ', topic word only' : ''})</span></label>)}
          </div>}
          {!approved ? <button className="primary" onClick={approve} disabled={busy}>Approve &amp; remember</button>
            : <div className="small"><span className="pill ok">approved</span> added {approved.added_things?.length || 0} things, {approved.added_people?.length || 0} people; remembered: {approved.remembered_topics?.join(', ') || 'none'}</div>}
        </div>
      )}
      <div className="row" style={{ marginTop: 12 }}>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="what did Ammamma say about…" style={{ flex: 1, minWidth: 200 }} onKeyDown={e => e.key === 'Enter' && search()} />
        <button onClick={search}>Search memory</button><span className="small muted">same endpoint the Muse connector uses</span>
      </div>
      {hits && <div style={{ marginTop: 6 }}>{hits.length === 0 && <div className="muted small">no matches</div>}{hits.map((h, i) => <div className="utt" key={i}><div className="who"><span>{h.kind} · {h.speaker || ''}</span><span>{h.when ? new Date(h.when).toLocaleString() : ''} · {h.score}</span></div><div>{h.text}</div></div>)}</div>}
    </div>
  )
}
