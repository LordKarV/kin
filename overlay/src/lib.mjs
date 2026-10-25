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

/**
 * Cards to pop up for one transcript: who each grounded name/kin term is, plus idiom/culture cards.
 * A person card is shown once per `ttlMs` so a grandparent saying "Ravi" ten times does not flood the screen.
 * Returns new state; `seen` is not mutated.
 */
export function cardsFor(t, seen, now, ttlMs = 120000) {
  const next = new Map(seen)
  const cards = []
  for (const g of t.grounded_spans || []) {
    if ((g.rendered || '').trim().toLowerCase() === (g.source || '').trim().toLowerCase()) continue // "pongal -> Pongal"
    const key = `who:${g.node_id}`
    if (now - (next.get(key) ?? -Infinity) < ttlMs) continue
    next.set(key, now)
    // family-graph people are slugged p_*; everything else is a place, dish, festival...
    cards.push({ kind: String(g.node_id).startsWith('p_') ? 'who' : 'what', title: g.source, body: g.rendered })
  }
  for (const c of t.pragmatics_cards || []) {
    const key = `card:${c.kind}:${c.source}`
    if (now - (next.get(key) ?? -Infinity) < ttlMs) continue
    next.set(key, now)
    cards.push({ kind: c.kind, title: c.source, body: c.meaning, literal: c.literal, why: c.why_it_matters })
  }
  return { cards, seen: next }
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
