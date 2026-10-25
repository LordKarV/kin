import { useState } from 'react'
import { api } from './api.ts'
import type { Role } from './api.ts'
import { KinCall } from './call.ts'
import CallScreen from './Call.tsx'
import Home from './Home.tsx'
import Join from './Join.tsx'
import { parseInvite } from './links.ts'

type Screen =
  | { name: 'home' }
  | { name: 'join' }
  | { name: 'call'; call: KinCall; familyId: number; peerLabel: string }
  | { name: 'ended' }

const invite = parseInvite(location.search)

export default function App() {
  const [screen, setScreen] = useState<Screen>(invite ? { name: 'join' } : { name: 'home' })

  /** Runs inside the tap handler: KinCall is built before the first await so iOS unlocks audio. */
  async function begin(role: Role, familyId: number, callId?: number, peerLabel = '') {
    const call = new KinCall()
    try {
      const j = await api.join({ family_id: familyId, role, call_id: callId })
      await call.connect(j)
    } catch (e) {
      await call.hangUp()
      throw e
    }
    setScreen({ name: 'call', call, familyId, peerLabel })
  }

  if (screen.name === 'call') return <CallScreen call={screen.call} familyId={screen.familyId} peerLabel={screen.peerLabel} onEnded={() => setScreen({ name: 'ended' })} />
  if (screen.name === 'ended') {
    return (
      <main className="screen center">
        <div className="brand big">KIN</div>
        <h1>Call ended</h1>
        <button className="primary pill wide" onClick={() => setScreen(invite ? { name: 'join' } : { name: 'home' })}>{invite ? 'Back' : 'Back home'}</button>
      </main>
    )
  }
  if (screen.name === 'join' && invite) return <Join invite={invite} onJoin={() => begin('grandparent', invite.family, invite.call)} />
  return <Home onCall={(familyId, name) => begin('grandchild', familyId, undefined, name)} />
}
