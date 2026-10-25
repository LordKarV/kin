// Pure helpers shared by the overlay windows and the tests. No Electron or DOM here.

export const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])

const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** English line as HTML, with Fade passthrough words (kept in the heritage language) marked. */
export function translationHtml(t) {
  const text = t.translation || ''
  const pts = (t.passthrough || []).filter(Boolean)
  if (!pts.length) return esc(text)
  const re = new RegExp(`(${pts.map(reEsc).join('|')})`, 'g')
  return text.split(re).map((part) => (pts.includes(part) ? `<mark class="pass">${esc(part)}</mark>` : esc(part))).join('')
}

// ---- cards -------------------------------------------------------------------
// Instant cards come from `glance` events (heard on ASR partials, before the translation); transcript grounded spans
// and `enrich` idiom cards share the same `seen` map so nothing is shown twice. Keys: glance item.key for people and
// things, `card:<kind>:<source>` for idiom/culture cards, and `title:<heard text>` so a term already on screen is not
// explained again by a late card.
const PICTURE_CATS = new Set(['food', 'festival', 'ritual', 'place', 'object'])
const CHIP = { saying: 'Saying', address: 'Address', idiom: 'Idiom', proverb: 'Saying', register: 'Address', honorific: 'Address', cultural: 'Culture' }
export const LIFETIME_MS = { info: 12000, compact: 9000, person: 9000 }
export const norm = (s) => String(s ?? '').trim().toLowerCase()
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : '')
const fresh = (seen, key, now, ttlMs) => now - (seen.get(key) ?? -Infinity) >= ttlMs

/** 'person' | 'ask' | 'info' (picture bubble) | 'compact' (meaning only). */
export function layoutFor(it) {
  if (it.kind === 'who') return 'person'
  if (it.kind === 'ask') return 'ask'
  if (PICTURE_CATS.has(it.category) || ((it.kind === 'what' || it.kind === 'term') && it.image_url)) return 'info'
  return 'compact'
}

/** Label chip text: the category for picture cards, Saying / Address / Idiom / Culture for meaning-only cards. */
export function chipFor(it) {
  const layout = layoutFor(it)
  if (layout === 'person') return 'Who is this'
  if (layout === 'ask') return 'New relative'
  if (layout === 'info') return cap(it.category) || 'What is this'
  return CHIP[it.category] || CHIP[it.kind] || (it.kind === 'what' ? 'What is this' : 'Culture')
}

const withLayout = (it) => ({ ...it, layout: layoutFor(it), chip: chipFor(it) })

/**
 * Cards and "Who is X?" questions for one `glance` event. Cards are deduped by item.key (once per `ttlMs`),
 * questions by normalized kin term in the same `asked` set asksFor uses. Returns new state; inputs are not mutated.
 */
export function glanceCardsFor(items, seen, asked, now, ttlMs = 120000) {
  const next = new Map(seen)
  const nextAsked = new Set(asked)
  const cards = []
  const asks = []
  for (const it of items || []) {
    if (!it?.key) continue
    if (it.kind === 'ask') {
      const term = it.term || it.title
      const key = norm(term)
      if (!key || nextAsked.has(key)) continue
      nextAsked.add(key)
      asks.push({ term, guess: it.guess || '', key })
      continue
    }
    if (!fresh(next, it.key, now, ttlMs)) continue
    next.set(it.key, now)
    next.set(`title:${norm(it.title)}`, now)
    cards.push(withLayout(it))
  }
  return { cards, asks, seen: next, asked: nextAsked }
}

/** A card item after its `glance_image` follow-up: picture added, body only filled if it had none. */
export function mergeImage(it, m) {
  return withLayout({
    ...it,
    image_url: m.image_url || it.image_url || '',
    image_credit: m.image_credit || it.image_credit || '',
    source_url: m.source_url || it.source_url || '',
    body: it.body || m.body || '',
  })
}

/**
 * Fallback cards from a transcript (grounded spans, when the glance missed them) and idiom/culture cards from a
 * transcript or `enrich` event. Each card shows once per `ttlMs`; a card for a term already explained is skipped.
 * Returns new state; `seen` is not mutated.
 */
export function cardsFor(t, seen, now, ttlMs = 120000) {
  const next = new Map(seen)
  const cards = []
  for (const g of t.grounded_spans || []) {
    if (norm(g.rendered) === norm(g.source)) continue // "pongal -> Pongal"
    // family-graph people are slugged p_*; everything else is a place, dish, festival... (same keys as glance items)
    const isWho = String(g.node_id).startsWith('p_')
    const key = isWho ? String(g.node_id) : `thing:${g.node_id}`
    if (!fresh(next, key, now, ttlMs)) continue
    next.set(key, now)
    next.set(`title:${norm(g.source)}`, now)
    cards.push(withLayout({ key, kind: isWho ? 'who' : 'what', title: g.source, body: g.rendered, category: '' }))
  }
  for (const c of t.pragmatics_cards || []) {
    const key = `card:${c.kind}:${c.source}`
    if (!fresh(next, key, now, ttlMs) || !fresh(next, `title:${norm(c.source)}`, now, ttlMs)) continue
    next.set(key, now)
    next.set(`title:${norm(c.source)}`, now)
    cards.push({ key, kind: c.kind, layout: 'compact', chip: CHIP[c.kind] || 'Culture', title: c.source, body: c.meaning, literal: c.literal, why: c.why_it_matters })
  }
  return { cards, seen: next }
}

/** Text as HTML with every heard term that has a card underlined (longest match first, case-insensitive). */
export function markTerms(text, terms) {
  const ts = [...new Set((terms || []).map((x) => String(x ?? '').trim()).filter(Boolean))].sort((a, b) => b.length - a.length)
  if (!ts.length) return esc(text)
  const set = new Set(ts.map(norm))
  const re = new RegExp(`(${ts.map(reEsc).join('|')})`, 'gi')
  return String(text ?? '').split(re).map((p) => (set.has(norm(p)) ? `<span class="heard">${esc(p)}</span>` : esc(p))).join('')
}

/** Re-chunk an arbitrary byte stream into fixed-size frames (100 ms of 16 kHz PCM16 = 3200 bytes). */
export function makeChunker(frameBytes, onFrame) {
  let pending = Buffer.alloc(0)
  return (chunk) => {
    pending = Buffer.concat([pending, chunk])
    while (pending.length >= frameBytes) {
      onFrame(pending.subarray(0, frameBytes))
      pending = pending.subarray(frameBytes)
    }
  }
}

/** Remote speakers to offer in the picker: everyone but the learner, oldest generation first. */
export function speakerChoices(graph) {
  return (graph.people || [])
    .filter((p) => !p.is_learner && !p.deceased)
    .sort((a, b) => (a.generation ?? 0) - (b.generation ?? 0))
    .map((p) => ({ id: p.id, label: `${p.name}${p.render ? ` (${p.render})` : ''}` }))
}

/**
 * Kin words the grandparent used that KIN could not place on the family graph ("Ravi mama" with no Ravi yet).
 * Each becomes a "Who is X?" card; the word before the kin term is offered as the name. Returns new state.
 */
export function asksFor(t, asked) {
  const next = new Set(asked)
  const asks = []
  for (const s of t.linker_spans || []) {
    // only relatives KIN has not met yet; generic uses (endearments, 'shopkeeper uncle') never ask
    if (s.type !== 'kin' || s.node_id || s.method !== 'unknown-relative') continue
    const key = (s.source || '').toLowerCase()
    if (!key || next.has(key)) continue
    next.add(key)
    const before = (t.src_text || '').slice(0, s.start).trim().split(/\s+/).pop() || ''
    asks.push({ term: s.source, guess: before.replace(/[.,!?;:"'“”‘’()]/g, ''), key })
  }
  return { asks, asked: next }
}
