import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Row = { lemma: string; p_known: number; n_exposures: number; n_verified: number; mastered: boolean }
type Sim = { weeks: number; sentence: string; passthrough: string[]; trajectories: { lemma: string; curve: number[]; mastered: boolean }[]; note: string }
type Rendered = { translation: string; passthrough: string[]; error: string | null }

export default function FadeTab() {
  const learner = 'p_arjun'
  const [rows, setRows] = useState<Row[]>([])
  const [weeks, setWeeks] = useState(1)
  const [sim, setSim] = useState<Sim | null>(null)
  const [rendered, setRendered] = useState<Rendered | null>(null)
  const [busy, setBusy] = useState(false)
  const load = () => api<Row[]>(`/api/fade/mastery?learner=${learner}`).then(setRows).catch(() => {})
  useEffect(() => { load() }, [])

  async function runSim(w: number) {
    setBusy(true); setWeeks(w)
    try {
      const s = await api<Sim>('/api/fade/simulate', { method: 'POST', body: JSON.stringify({ learner, weeks: w }) })
      setSim(s); await load()
      const r = await api<Rendered>('/api/translate/grounded', { method: 'POST', body: JSON.stringify({ text: s.sentence, speaker: 'p_kamala', listener: learner }) })
      setRendered(r)
    } finally { setBusy(false) }
  }
  async function resetAll() { await api('/api/fade/reset', { method: 'POST', body: JSON.stringify({ learner }) }); setSim(null); setRendered(null); load() }

  return (
    <>
      <div className="panel">
        <h2>Fade · the translation gets out of the way as Arjun learns</h2>
        <div className="muted small">Every heritage word Arjun hears with its translation is a weak exposure; every “got it” tap is a verified observation. Bayesian Knowledge Tracing per word. At p(known) ≥ 0.85 the word passes through untranslated.</div>
        <div className="row" style={{ marginTop: 10 }}>
          <label>Weeks of calls (simulation of accumulated history): <b>{weeks}</b></label>
          <input type="range" min={0} max={8} value={weeks} onChange={e => runSim(Number(e.target.value))} disabled={busy} style={{ width: 240 }} />
          <button onClick={() => runSim(1)} disabled={busy}>Week 1</button>
          <button className="primary" onClick={() => runSim(8)} disabled={busy}>Week 8</button>
          <button className="danger" onClick={resetAll} disabled={busy}>Reset</button>
        </div>
        {sim && <div className="small muted" style={{ marginTop: 6 }}>⚠ {sim.note}</div>}
      </div>

      {sim && (
        <div className="panel">
          <h2>The same sentence at week {sim.weeks}</h2>
          <div className="utt gp">
            <div className="src">{highlight(sim.sentence, sim.passthrough)}</div>
            <div className="tr">{rendered ? highlight(rendered.translation, rendered.passthrough) : <span className="muted">rendering…</span>}</div>
            <div className="small muted">{sim.passthrough.length} word{sim.passthrough.length === 1 ? '' : 's'} left in Tamil: {sim.passthrough.join(', ') || 'none yet'}{rendered?.error ? ' · model unavailable, linker-only rendering' : ''}</div>
          </div>
        </div>
      )}

      {sim && (
        <div className="panel">
          <h2>Mastery curves (week 0 → {sim.weeks})</h2>
          <Curves sim={sim} />
        </div>
      )}

      <div className="panel">
        <h2>Current mastery · {rows.length} words tracked</h2>
        {rows.length === 0 && <div className="muted">Nothing tracked yet. Join a call as the grandchild, or run the simulation.</div>}
        <div className="mastery">
          {rows.map(r => (
            <div className="w" key={r.lemma} title={`${r.n_exposures} exposures · ${r.n_verified} verified`}>
              <div className="row" style={{ justifyContent: 'space-between' }}><span>{r.lemma}</span><span className={`small ${r.mastered ? 'ok' : 'muted'}`}>{(100 * r.p_known).toFixed(0)}%{r.mastered ? ' ✓' : ''}</span></div>
              <div className="bar"><i style={{ width: `${100 * r.p_known}%`, background: r.mastered ? 'var(--accent2)' : 'var(--accent)' }} /></div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

function highlight(text: string, pts: string[]) {
  if (!pts.length) return <>{text}</>
  const re = new RegExp(`(${pts.map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g')
  return <>{text.split(re).map((part, i) => pts.includes(part) ? <mark key={i} className="pass">{part}</mark> : part)}</>
}

function Curves({ sim }: { sim: Sim }) {
  const W = 640, H = 220, pad = 28
  const n = sim.trajectories[0]?.curve.length || 1
  const x = (i: number) => pad + (i * (W - 2 * pad)) / Math.max(1, n - 1)
  const y = (p: number) => H - pad - p * (H - 2 * pad)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 760 }}>
      <line x1={pad} x2={W - pad} y1={y(0.85)} y2={y(0.85)} stroke="#5ad1b3" strokeDasharray="4 4" />
      <text x={W - pad} y={y(0.85) - 4} fill="#5ad1b3" fontSize="11" textAnchor="end">passthrough threshold 0.85</text>
      {[0, 0.5, 1].map(v => <text key={v} x={4} y={y(v) + 4} fill="#9aa3b2" fontSize="10">{v}</text>)}
      {sim.trajectories.map((t, k) => (
        <polyline key={t.lemma} fill="none" stroke={t.mastered ? '#5ad1b3' : `hsl(${(k * 37) % 360} 60% 65%)`} strokeWidth={t.mastered ? 2 : 1}
          points={t.curve.map((p, i) => `${x(i)},${y(p)}`).join(' ')}><title>{t.lemma}</title></polyline>
      ))}
      {Array.from({ length: n }).map((_, i) => <text key={i} x={x(i)} y={H - 8} fill="#9aa3b2" fontSize="10" textAnchor="middle">w{i}</text>)}
    </svg>
  )
}
