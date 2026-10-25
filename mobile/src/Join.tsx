import { useEffect, useState } from 'react'
import { api, errText } from './api.ts'
import { PhoneIcon } from './icons.tsx'
import type { Invite } from './links.ts'
import { langLabel } from './links.ts'

interface Props { invite: Invite; onJoin: () => Promise<void> }

/** The grandparent's first screen: one big button (the tap is what lets iOS play audio). */
export default function Join({ invite, onJoin }: Props) {
  const [lang, setLang] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.families()
      .then((fs) => { const f = fs.find((x) => x.id === invite.family); if (f) setLang(f.heritage_lang) })
      .catch(() => {}) // the label is cosmetic; joining still works
  }, [invite.family])

  async function join() {
    setBusy(true)
    setErr('')
    try { await onJoin() } catch (e) { setErr(errText(e)); setBusy(false) }
  }

  return (
    <main className="screen center" lang={lang || undefined}>
      <div className="brand big">KIN</div>
      {lang && <div className="lang-label">{langLabel(lang)}</div>}
      <button className="join" onClick={join} disabled={busy} aria-label="Join call">
        <PhoneIcon />
        <span>Join call</span>
      </button>
      {err && <p className="msg" role="alert">{err}</p>}
    </main>
  )
}
