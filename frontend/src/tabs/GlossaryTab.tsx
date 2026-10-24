import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Entry = { id: number; card: { kind: string; source: string; literal: string; meaning: string; why_it_matters: string }; speaker: string | null; created_at: string; audio_url: string; src_text: string }

export default function GlossaryTab() {
  const [rows, setRows] = useState<Entry[]>([])
  useEffect(() => { api<Entry[]>('/api/glossary').then(setRows).catch(() => {}) }, [])
  return (
    <div className="panel">
      <h2>Glossary · every card ever shown</h2>
      {rows.length === 0 && <div className="muted">No cards yet. They appear when a literal translation would have lost meaning (idiom, proverb, register).</div>}
      {rows.map(r => (
        <div className="utt" key={r.id}>
          <div className="who"><span>{r.card.kind} · {r.speaker || 'someone'}</span><span>{new Date(r.created_at).toLocaleString()}</span></div>
          <div className="src">“{r.card.source}”</div>
          <div><b>Literal:</b> {r.card.literal}</div><div><b>Means:</b> {r.card.meaning}</div>
          <div className="small muted">{r.card.why_it_matters}{r.src_text ? ` · said in: ${r.src_text}` : ''}</div>
          {r.audio_url && <audio controls src={r.audio_url} style={{ marginTop: 6, width: '100%' }} />}
        </div>
      ))}
    </div>
  )
}
