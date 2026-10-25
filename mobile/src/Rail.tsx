import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, errText } from './api.ts'
import type { Relation } from './api.ts'
import { SKELETON_MS, answerAsk, dismiss, isHttps, norm } from './cards.ts'
import type { Ask, Card, RailEntry } from './cards.ts'
import { CheckIcon, CloseIcon } from './icons.tsx'

interface Props { rail: RailEntry[]; now: number; familyId: number; setRail: (f: (r: RailEntry[]) => RailEntry[]) => void }

let relationsP: Promise<Relation[]> | null = null // cached once; a failed load is retried by the next card
const relations = () => (relationsP ??= api.relations().catch(() => { relationsP = null; return [] }))

const Chip = ({ text, onClose }: { text: string; onClose: () => void }) => (
  <div className="kind"><span className="chip">{text}</span><button className="icon" onClick={onClose} aria-label="Dismiss"><CloseIcon /></button></div>
)

function Title({ c }: { c: Card }) {
  return <div className="title">{c.title}{c.native && norm(c.native) !== norm(c.title) && <> <span className="native">{c.native}</span></>}</div>
}

function Picture({ c, age }: { c: Card; age: number }) {
  const [broken, setBroken] = useState(false)
  if (broken) return null // a broken picture leaves a complete text card
  if (!isHttps(c.image_url)) return age < SKELETON_MS ? <div className="pic skeleton" /> : null
  return <div className="pic"><img src={c.image_url} alt={c.title || ''} loading="lazy" onError={() => setBroken(true)} /></div>
}

function CardView({ c, age, onClose }: { c: Card; age: number; onClose: () => void }) {
  if (c.layout === 'person') {
    return (
      <article className={`card panel person ${c.kind}`}>
        <div className="avatar" aria-hidden="true">{[...(c.title || '?')][0].toUpperCase()}</div>
        <div className="main"><Chip text={c.chip} onClose={onClose} /><Title c={c} />{c.body && <div className="body">{c.body}</div>}</div>
      </article>
    )
  }
  const credit = [c.image_credit, c.source_url && 'Wikipedia'].filter(Boolean).join(' / ')
  return (
    <article className={`card panel ${c.layout} ${c.kind}`}>
      {c.layout === 'info' && <Picture c={c} age={age} />}
      <Chip text={c.chip} onClose={onClose} />
      <Title c={c} />
      {c.body && <div className="body">{c.body}</div>}
      {c.literal && <div className="why">Literally: {c.literal}</div>}
      {c.why && <div className="why">{c.why}</div>}
      {c.layout === 'info' && credit && <div className="credit">{credit}</div>}
    </article>
  )
}

function AskView({ a, familyId, answered, onClose, onAnswered }: { a: Ask; familyId: number; answered?: string; onClose: () => void; onAnswered: (r: string) => void }) {
  const [sug, setSug] = useState<Relation[]>([])
  const [rels, setRels] = useState<Relation[] | null>(null)
  const [path, setPath] = useState('')
  const [name, setName] = useState(a.guess)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    Promise.all([api.suggest(a.term, familyId).catch(() => [] as Relation[]), relations()]).then(([s, r]) => {
      setSug(s)
      setRels(r.filter((x) => !s.some((y) => y.path === x.path)))
      setPath(s[0]?.path || '')
    })
  }, [a.term, familyId])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!path) return setMsg('Pick how they are related to you.')
    if (!name.trim()) return setMsg('Add their name.')
    setBusy(true)
    setMsg('')
    try {
      const p = await api.addRelative({ family_id: familyId, path, name: name.trim(), you_call_them: a.term })
      onAnswered(p.render || p.name || name.trim())
    } catch (err) {
      setMsg(`Could not add: ${errText(err)}`)
      setBusy(false)
    }
  }

  const who = [a.guess, a.term].filter(Boolean).join(' ')
  return (
    <article className="card panel ask">
      <Chip text="New relative" onClose={onClose} />
      <div className="title">Who is &lsquo;{who}&rsquo;?</div>
      {answered ? (
        <div className="done"><CheckIcon /><span>Added: <b>{answered}</b></span></div>
      ) : (
        <form onSubmit={submit} noValidate>
          <label className="field"><span>How are they related to you?</span>
            <select value={path} onChange={(e) => setPath(e.target.value)}>
              {rels == null && <option value="">Loading</option>}
              {rels != null && !sug.length && <option value="">Pick a relation</option>}
              {sug.length > 0 && <optgroup label={`What "${a.term}" usually means`}>{sug.map((r) => <option key={r.path} value={r.path} title={r.gloss}>{r.label}</option>)}</optgroup>}
              {rels && rels.length > 0 && <optgroup label={sug.length ? 'Other relations' : 'Relations'}>{rels.map((r) => <option key={r.path} value={r.path}>{r.label}</option>)}</optgroup>}
            </select>
          </label>
          <label className="field"><span>Their name</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" /></label>
          {msg && <div className="msg" role="alert">{msg}</div>}
          <div className="actions">
            <button type="button" className="pill" onClick={onClose} disabled={busy}>Not family</button>
            <button type="submit" className="pill primary" disabled={busy}>Add</button>
          </div>
        </form>
      )}
    </article>
  )
}

/** Newest first, at most MAX_CARDS (cards.ts enforces it); idle cards fade out on their own. */
export default function Rail({ rail, now, familyId, setRail }: Props) {
  return (
    <section className="rail">
      {rail.map((e) => {
        const close = () => setRail((r) => dismiss(r, e.id))
        return e.ask
          ? <AskView key={e.id} a={e.ask} familyId={familyId} answered={e.answered} onClose={close} onAnswered={(text) => setRail((r) => answerAsk(r, e.id, text, Date.now()))} />
          : <CardView key={e.id} c={e.card!} age={now - e.at} onClose={close} />
      })}
    </section>
  )
}
