import { asksFor, cardsFor, esc } from './lib.mjs'
const LIFETIME_MS = 25000
const ANSWERED_MS = 8000
const HOVER_RECHECK_MS = 3000
const MAX_CARDS = 5
const LABEL = { who: 'Who is this', what: 'What is this', idiom: 'Idiom', proverb: 'Proverb', register: 'Tone', honorific: 'Honorific', cultural: 'Culture' }
const ICON_X = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 3.5l9 9m0-9l-9 9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'
const ICON_OK = '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="9" fill="currentColor"/><path d="M6 10.5l2.6 2.5L14 7.5" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>'
const dismissBtn = `<button type="button" class="icon" aria-label="Dismiss" title="Dismiss">${ICON_X}</button>`
const stack = document.getElementById('stack')
let seen = new Map()
let asked = new Set()
let hovering = false
let familyId = null
let relationsP = null

const errText = (e) => String(e?.message ?? e).replace(/^Error invoking remote method '[^']+': (Error: )?/, '')
// cached once; a failed load is retried by the next card
const relations = () => (relationsP ??= window.kin.relations().catch(() => { relationsP = null; return [] }))

// control announces the family on load; this covers the case where that message beat this listener
window.kin.families().then((f) => { if (familyId == null && f.length) familyId = f[0].id }).catch(() => {})

// cards are click-through until the pointer is over one (so the call underneath stays usable)
stack.addEventListener('mouseenter', () => { hovering = true; window.kin.mouse(true) })
stack.addEventListener('mouseleave', () => { hovering = false; window.kin.mouse(false) })

const report = () => window.kin.cards(stack.children.length)
function remove(el) { el.remove(); report() }
function expireAfter(el, ms) {
  const tick = () => (hovering ? setTimeout(tick, HOVER_RECHECK_MS) : remove(el)) // never vanish under the cursor
  setTimeout(tick, ms)
}
// over the cap, drop the oldest info card first; unanswered questions go last
function trim() {
  while (stack.children.length > MAX_CARDS) {
    const info = [...stack.children].filter((c) => !c.classList.contains('ask') || c.classList.contains('answered'))
    ;(info.pop() || stack.lastElementChild).remove()
  }
}
function push(el) { stack.prepend(el); trim(); report() }

function add(c) {
  const el = document.createElement('div')
  el.className = `card panel ${c.kind}`
  el.innerHTML = `<div class="kind">${esc(LABEL[c.kind] || c.kind)}${dismissBtn}</div>`
    + `<div class="title">${esc(c.title)}</div><div class="body">${esc(c.body)}</div>`
    + (c.literal ? `<div class="why">Literally: ${esc(c.literal)}</div>` : '')
    + (c.why ? `<div class="why">${esc(c.why)}</div>` : '')
  el.querySelector('button').onclick = () => remove(el)
  expireAfter(el, LIFETIME_MS)
  push(el)
}

// ---- "Who is X?" cards: stay until answered or dismissed ---------------------
function addAsk(a) {
  const el = document.createElement('div')
  el.className = 'card panel ask'
  const who = [a.guess, a.term].filter(Boolean).join(' ')
  el.innerHTML = `<div class="kind">New relative${dismissBtn}</div>`
    + `<div class="title">Who is ‘${esc(who)}’?</div>`
    + '<form novalidate>'
    + '<label class="field"><span>How are they related to you?</span><select name="path"><option value="">Loading…</option></select></label>'
    + `<label class="field"><span>Their name</span><input name="name" placeholder="Name" value="${esc(a.guess)}" /></label>`
    + '<div class="msg" role="alert"></div>'
    + '<div class="actions"><button type="button" data-act="no">Not family</button><button type="submit" class="primary">Add</button></div>'
    + '</form>'
  const form = el.querySelector('form')
  el.querySelector('.kind button').onclick = () => remove(el)
  form.querySelector('[data-act="no"]').onclick = () => remove(el)
  form.onsubmit = (e) => { e.preventDefault(); submitAsk(el, form, a.term) }
  push(el)
  fillRelations(form.elements.path, a.term)
}

function group(label, items) {
  const g = document.createElement('optgroup')
  g.label = label
  for (const r of items) { const o = new Option(r.label, r.path); if (r.gloss) o.title = r.gloss; g.append(o) }
  return g
}

async function fillRelations(select, term) {
  const [sug, rels] = await Promise.all([
    familyId == null ? [] : window.kin.suggest(term, familyId).catch(() => []),
    relations(),
  ])
  const rest = rels.filter((r) => !sug.some((s) => s.path === r.path))
  select.innerHTML = ''
  if (sug.length) select.append(group(`What "${term}" usually means`, sug))
  if (rest.length) select.append(group(sug.length ? 'Other relations' : 'Relations', rest))
  if (!select.options.length) select.add(new Option('Could not load relations', ''))
}

async function submitAsk(el, form, term) {
  const msg = form.querySelector('.msg')
  const path = form.elements.path.value
  const name = form.elements.name.value.trim()
  if (!path) { msg.textContent = 'Pick how they are related to you.'; return form.elements.path.focus() }
  if (!name) { msg.textContent = 'Add their name.'; return form.elements.name.focus() }
  if (familyId == null) { msg.textContent = 'Pick a family in the KIN panel first.'; return }
  const buttons = [...form.querySelectorAll('button')]
  buttons.forEach((b) => { b.disabled = true })
  msg.textContent = ''
  try {
    const p = await window.kin.addRelative({ family_id: Number(familyId), path, name, you_call_them: term })
    const done = document.createElement('div')
    done.className = 'done'
    done.innerHTML = `${ICON_OK}<span>Added: <b>${esc(p.render || p.name || name)}</b></span>`
    form.replaceWith(done)
    el.classList.add('answered')
    expireAfter(el, ANSWERED_MS)
  } catch (e) {
    msg.textContent = `Could not add: ${errText(e)}`
    buttons.forEach((b) => { b.disabled = false })
  }
}

window.kin.on((m) => {
  if (m.type === 'family') {
    if (String(m.familyId) !== String(familyId)) asked = new Set() // kin words are per family
    familyId = m.familyId
    return
  }
  if (m.type !== 'transcript' || m.role !== 'grandparent') return
  const r = cardsFor(m, seen, Date.now())
  seen = r.seen
  r.cards.forEach(add)
  const q = asksFor(m, asked)
  asked = q.asked
  q.asks.forEach(addAsk)
  report()
})
