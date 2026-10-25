import { useEffect, useState } from 'react'
import { api, elderOf, errText } from './api.ts'
import type { Family, Person } from './api.ts'
import { PhoneIcon } from './icons.tsx'
import Setup from './Setup.tsx'

interface Props { onCall: (familyId: number, elderName: string) => Promise<void> }

export default function Home({ onCall }: Props) {
  const [families, setFamilies] = useState<Family[] | null>(null)
  const [familyId, setFamilyId] = useState<number | null>(null)
  const [elder, setElder] = useState<Person | null>(null)
  const [setup, setSetup] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function load(select?: number) {
    setErr('')
    try {
      const fs = await api.families()
      setFamilies(fs)
      setFamilyId(select ?? fs[0]?.id ?? null)
    } catch (e) {
      setErr(`Cannot reach KIN: ${errText(e)}`)
    }
  }
  useEffect(() => { load() }, [])

  useEffect(() => {
    setElder(null)
    if (familyId == null) return
    api.graph(familyId).then((g) => setElder(elderOf(g) ?? null)).catch((e) => setErr(errText(e)))
  }, [familyId])

  async function call() {
    if (familyId == null) return
    setBusy(true)
    setErr('')
    try { await onCall(familyId, elder?.name || '') } catch (e) { setErr(`Could not start the call: ${errText(e)}`); setBusy(false) }
  }

  if (families == null) {
    return (
      <main className="screen center">
        <div className="brand big">KIN</div>
        {err ? <><p className="msg" role="alert">{err}</p><button className="pill" onClick={() => load()}>Try again</button></> : <p className="muted">Loading</p>}
      </main>
    )
  }
  if (setup || !families.length) {
    return <Setup cancelable={families.length > 0} onCancel={() => setSetup(false)} onDone={(id) => { setSetup(false); load(id) }} />
  }

  return (
    <main className="screen">
      <header className="bar"><span className="brand">KIN</span></header>
      <section className="panel stack">
        <label className="field">
          <span>Family</span>
          <select value={familyId ?? ''} onChange={(e) => setFamilyId(Number(e.target.value))}>
            {families.map((f) => <option key={f.id} value={f.id}>{f.name} ({f.language})</option>)}
          </select>
        </label>
        {elder?.render && <p className="hint">{elder.render}</p>}
      </section>
      <div className="grow" />
      {err && <p className="msg" role="alert">{err}</p>}
      <button className="call-btn" onClick={call} disabled={busy || familyId == null}>
        <PhoneIcon />
        <span>{busy ? 'Calling' : `Call ${elder?.name || 'them'}`}</span>
      </button>
      <button className="link" onClick={() => setSetup(true)}>Set up another family</button>
    </main>
  )
}
