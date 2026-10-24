import { useEffect, useState } from 'react'
import { api, type Person, type Edge, type Thing } from '../lib/api'

type Graph = { learner: string; heritage_lang: string; people: (Person & { generation: number })[]; edges: Edge[]; things: Thing[] }

export default function GraphTab() {
  const [g, setG] = useState<Graph | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api<Graph>('/api/family/graph').then(setG).catch(e => setErr(String(e))) }, [])
  if (err) return <div className="panel err">{err}</div>
  if (!g) return <div className="panel muted">Loading…</div>
  const gens = [...new Set(g.people.map(p => p.generation))].sort((a, b) => a - b)
  const label: Record<number, string> = { [-2]: 'Grandparents', [-1]: 'Parents, uncles & aunts', 0: 'Grandchildren & cousins' }
  const termFor = (p: Person) => p.render.match(/^your [a-z- ]+? ([A-Za-z]+ [a-z ]+?) \(/)?.[1] || ''
  return (
    <>
      <div className="panel">
        <h2>The family, as {g.people.find(p => p.id === g.learner)?.name} hears it</h2>
        <div className="tree">
          {gens.map(gen => (
            <div key={gen}>
              <div className="small muted" style={{ marginBottom: 6 }}>{label[gen] ?? `generation ${gen}`}</div>
              <div className="gen">
                {g.people.filter(p => p.generation === gen).map(p => (
                  <div key={p.id} className={`person ${p.is_learner ? 'learner' : ''} ${p.id === 'p_kamala' ? 'speaker' : ''}`} title={p.notes}>
                    <div className="n">{p.name} <span className="muted">{p.lang_name}</span>{p.deceased ? ' ✝' : ''}</div>
                    <div className="t">{termFor(p) || (p.is_learner ? 'the learner' : '')}</div>
                    <div className="r">{p.render}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <h2>Kin terms on the edges</h2>
        <div className="small">{g.edges.filter(e => e.lang_term).map((e, i) => <span key={i} className="pill">{g.people.find(p => p.id === e.dst)?.name} calls {g.people.find(p => p.id === e.src)?.name} “{e.lang_term}”</span>)}</div>
      </div>
      <div className="panel">
        <h2>Dishes, places, events</h2>
        {g.things.map(t => <div key={t.id} className="utt"><div className="who"><span>{t.kind}</span><span>{t.aliases.slice(0, 4).join(' · ')}</span></div><div className="src">{t.name} <span className="muted">{t.lang_name}</span></div><div className="small muted">{t.note}</div></div>)}
      </div>
    </>
  )
}
