import { esc, markTerms, translationHtml } from './lib.mjs'
const KEEP = 2
const MAX_TERMS = 40
let recent = []
let heard = [] // titles that got a card this call, underlined in the caption
const names = {}
const loadNames = (familyId) => window.kin.graph(familyId).then((g) => g.people.forEach((p) => { names[p.id] = p.name })).catch(() => {})
// names load when the control panel selects a family; with nothing set up yet there is nothing to ask for
window.kin.on((m) => { if (m.type === 'family') loadNames(m.familyId) })

function render() {
  document.getElementById('lines').innerHTML = recent.map((t, i) => {
    const old = i < recent.length - 1
    return `<div class="${old ? 'line old' : 'line'}">${old ? '' : `<div class="who">${esc(names[t.speaker] || t.speaker)}</div>`}`
      + `${translationHtml(t)}${old ? '' : `<div class="src">${markTerms(t.src_text, heard)}</div>`}</div>`
  }).join('')
}
window.kin.on((m) => {
  if (m.type === 'glance') {
    heard = [...heard, ...(m.items || []).map((it) => it.title).filter(Boolean)].slice(-MAX_TERMS)
    const p = document.getElementById('partial')
    p.innerHTML = markTerms(p.textContent, heard)
    if (recent.length) render()
  }
  if (m.type === 'partial') document.getElementById('partial').innerHTML = markTerms(m.text, heard)
  if (m.type === 'transcript' && m.role === 'grandparent') {
    recent = [...recent, m].slice(-KEEP)
    document.getElementById('partial').textContent = ''
    render()
  }
})
