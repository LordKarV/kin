import type { Transcript as T } from '../lib/api'

/** Highlight grounded spans (hover = who this is) and passthrough tokens in the source line. */
export function Highlight({ t }: { t: T }) {
  const spans = [...(t.linker_spans || [])].filter(s => s.node_id).sort((a, b) => a.start - b.start)
  const out: React.ReactNode[] = []
  let pos = 0
  spans.forEach((s, i) => {
    if (s.start < pos) return
    out.push(t.src_text.slice(pos, s.start))
    out.push(<mark key={i} className="ground" title={`${s.rendered}${s.candidates.length > 1 ? `  · chose among: ${s.candidates.join(', ')}` : ''}`}>{t.src_text.slice(s.start, s.end)}</mark>)
    pos = s.end
  })
  out.push(t.src_text.slice(pos))
  return <>{out}</>
}

export function Translation({ t }: { t: T }) {
  // underline passthrough tokens kept in the heritage language
  const pts = t.passthrough || []
  if (!pts.length) return <>{t.translation}</>
  const re = new RegExp(`(${pts.map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g')
  return <>{t.translation.split(re).map((part, i) => pts.includes(part) ? <mark key={i} className="pass" title="You know this word: left untranslated (Fade)">{part}</mark> : part)}</>
}

export function Latency({ lat }: { lat: Record<string, number> }) {
  const parts: [string, number, string][] = [['asr', lat.asr_ms || 0, '#6b7a99'], ['link', lat.link_ms || 0, '#5ad1b3'], ['mt', lat.mt_ms || 0, '#f2b84b'], ['tts', lat.tts_first_byte_ms || 0, '#c678dd']]
  const total = Math.max(1, parts.reduce((a, p) => a + p[1], 0))
  return (
    <div className="lat">
      <div className="latbar">{parts.map(([k, v, c]) => <span key={k} style={{ width: `${(100 * v) / total}%`, background: c }} title={`${k} ${v.toFixed(0)} ms`} />)}</div>
      {parts.map(([k, v]) => <span key={k} className="pill">{k} {v.toFixed(0)} ms</span>)}<span className="pill">total {(lat.total_ms || 0).toFixed(0)} ms</span>
    </div>
  )
}

export function Utterance({ t, names, onVerify, verified }: { t: T; names: Record<string, string>; onVerify?: (id: number, ok: boolean) => void; verified?: boolean | null }) {
  return (
    <div className={`utt ${t.role === 'grandparent' ? 'gp' : 'gc'}`}>
      <div className="who"><span>{names[t.speaker] || t.speaker} → {names[t.listener] || t.listener}</span><span>#{t.utterance_id}{t.error ? <span className="err"> · fallback</span> : null}</span></div>
      <div className="src"><Highlight t={t} /></div>
      <div className="tr"><Translation t={t} /></div>
      {t.grounded_spans?.length ? <div className="small muted">{t.grounded_spans.map((s, i) => <span key={i} className="pill ok">{s.source} → {s.rendered}</span>)}</div> : null}
      {t.pragmatics_cards?.map((c, i) => (
        <div className="card" key={i}><div className="kind">{c.kind} · “{c.source}”</div><div><b>Literal:</b> {c.literal}</div><div><b>Means:</b> {c.meaning}</div><div className="muted small">{c.why_it_matters}</div></div>
      ))}
      <Latency lat={t.latencies || {}} />
      {onVerify && t.target_lang === 'en' && (
        <div className="row small" style={{ marginTop: 6 }}>
          <span className="muted">Did you get it without the translation?</span>
          {verified == null ? (<><button onClick={() => onVerify(t.utterance_id, true)}>👍 got it</button><button onClick={() => onVerify(t.utterance_id, false)}>👎 needed it</button></>)
            : <span className="pill ok">{verified ? 'verified: understood' : 'noted: needed translation'}</span>}
        </div>
      )}
    </div>
  )
}
