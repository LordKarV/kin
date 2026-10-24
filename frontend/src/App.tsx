import { useEffect, useState } from 'react'
import CallTab from './tabs/CallTab'
import GraphTab from './tabs/GraphTab'
import GlossaryTab from './tabs/GlossaryTab'
import FadeTab from './tabs/FadeTab'

const TABS = ['Call', 'Family', 'Glossary', 'Fade'] as const
type Tab = typeof TABS[number]

export default function App() {
  const [tab, setTab] = useState<Tab>((location.hash.replace('#', '') as Tab) || 'Call')
  const go = (t: Tab) => { setTab(t); location.hash = t }
  useEffect(() => { const h = () => { const t = location.hash.replace('#', '') as Tab; if (TABS.includes(t)) setTab(t) }; addEventListener('hashchange', h); return () => removeEventListener('hashchange', h) }, [])
  return (
    <div className="app">
      <header className="top">
        <h1>KIN</h1>
        <span className="tag">a translator that knows your family, and fades</span>
        <nav className="tabs">{TABS.map(t => <button key={t} className={t === tab ? 'active' : ''} onClick={() => go(t)}>{t}</button>)}</nav>
      </header>
      {tab === 'Call' && <CallTab />}
      {tab === 'Family' && <GraphTab />}
      {tab === 'Glossary' && <GlossaryTab />}
      {tab === 'Fade' && <FadeTab />}
    </div>
  )
}
