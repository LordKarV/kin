import { esc, translationHtml } from './lib.mjs'
const KEEP = 2
let recent = []
const names = {}
const loadNames = (familyId) => window.kin.graph(familyId).then((g) => g.people.forEach((p) => { names[p.id] = p.name })).catch(() => {})
// names load when the control panel selects a family; with nothing set up yet there is nothing to ask for
window.kin.on((m) => { if (m.type === 'family') loadNames(m.familyId) })

function render() {
  document.getElementById('lines').innerHTML = recent.map((t, i) => {
    const old = i < recent.length - 1
    return `<div class="${old ? 'line old' : 'line'}">${old ? '' : `<div class="who">${esc(names[t.speaker] || t.speaker)}</div>`}`
      + `${translationHtml(t)}${old ? '' : `<div class="src">${esc(t.src_text)}</div>`}</div>`
  }).join('')
}
window.kin.on((m) => {
  if (m.type === 'partial') document.getElementById('partial').textContent = m.text
  if (m.type === 'transcript' && m.role === 'grandparent') {
    recent = [...recent, m].slice(-KEEP)
    document.getElementById('partial').textContent = ''
    render()
  }
})
