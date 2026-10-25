import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, errText } from './api.ts'
import type { Language, Relation } from './api.ts'

const DEFAULT_LANG = 'ta'
const DEFAULT_RELATION = 'mother.mother'
const REQUIRED: [keyof Fields, string][] = [
  ['language', 'the language they speak'],
  ['your_name', 'your name'],
  ['their_name', 'who you are calling'],
  ['you_call_them', 'what you call them'],
  ['relation', 'how they are related to you'],
]
interface Fields { language: string; your_name: string; their_name: string; you_call_them: string; relation: string }
interface Props { cancelable: boolean; onCancel: () => void; onDone: (familyId: number) => void }

/** Same fields as the overlay setup: start with one person, KIN learns the rest from calls. */
export default function Setup({ cancelable, onCancel, onDone }: Props) {
  const [langs, setLangs] = useState<Language[]>([])
  const [rels, setRels] = useState<Relation[]>([])
  const [f, setF] = useState<Fields>({ language: '', your_name: '', their_name: '', you_call_them: '', relation: '' })
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    Promise.all([api.languages(), api.relations()])
      .then(([ls, rs]) => {
        const avail = ls.filter((l) => l.available)
        setLangs(avail)
        setRels(rs)
        setF((x) => ({
          ...x,
          language: avail.some((l) => l.code === DEFAULT_LANG) ? DEFAULT_LANG : avail[0]?.code || '',
          relation: rs.some((r) => r.path === DEFAULT_RELATION) ? DEFAULT_RELATION : rs[0]?.path || '',
        }))
      })
      .catch((e) => setMsg(`Cannot load languages: ${errText(e)}`))
  }, [])

  const set = (k: keyof Fields) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    const missing = REQUIRED.find(([k]) => !f[k].trim())
    if (missing) return setMsg(`Please add ${missing[1]}.`)
    setBusy(true)
    setMsg('')
    try {
      const r = await api.setup({ ...f, your_name: f.your_name.trim(), their_name: f.their_name.trim(), you_call_them: f.you_call_them.trim() })
      onDone(r.family_id)
    } catch (err) {
      setMsg(`Could not create the family: ${errText(err)}`)
      setBusy(false)
    }
  }

  return (
    <main className="screen">
      <header className="bar"><span className="brand">KIN</span></header>
      <form className="panel stack" onSubmit={submit} noValidate>
        <div>
          <h1>Set up your family</h1>
          <p className="hint">Start with one person. KIN learns the rest of your family from your calls.</p>
        </div>
        <label className="field"><span>Language they speak</span>
          <select value={f.language} onChange={set('language')}>
            {langs.map((l) => <option key={l.code} value={l.code}>{l.native_name && l.native_name !== l.name ? `${l.name} (${l.native_name})` : l.name}</option>)}
          </select>
        </label>
        <label className="field"><span>Your name</span><input value={f.your_name} onChange={set('your_name')} autoComplete="given-name" /></label>
        <label className="field"><span>Who are you calling?</span><input value={f.their_name} onChange={set('their_name')} placeholder="Their name" /></label>
        <label className="field"><span>What do you call them?</span><input value={f.you_call_them} onChange={set('you_call_them')} placeholder="e.g. Paatti, Nani, Abuela" /></label>
        <label className="field"><span>How are they related to you?</span>
          <select value={f.relation} onChange={set('relation')}>
            {rels.map((r) => <option key={r.path} value={r.path}>{r.label}</option>)}
          </select>
        </label>
        {msg && <div className="msg" role="alert">{msg}</div>}
        <div className="actions">
          {cancelable && <button type="button" className="pill" onClick={onCancel}>Cancel</button>}
          <button type="submit" className="pill primary" disabled={busy}>{busy ? 'Creating' : 'Create family'}</button>
        </div>
      </form>
    </main>
  )
}
