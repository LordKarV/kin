// Pure card and caption logic for the grandchild's call screen. No DOM, no LiveKit: tested with node --test.
// Ported from overlay/src/lib.mjs + overlay/src/cards.js so both surfaces show the same cards with the same pacing.

export type Role = 'grandchild' | 'grandparent'
export type Layout = 'person' | 'ask' | 'info' | 'compact'

export interface GlanceItem {
  key: string
  kind: string // who | what | term | saying | ask (and idiom kinds on enrich cards)
  title?: string
  native?: string
  body?: string
  category?: string
  image_url?: string
  image_credit?: string
  source_url?: string
  term?: string
  guess?: string
}
export interface Card extends GlanceItem { layout: Layout; chip: string; literal?: string; why?: string }
export interface Ask { term: string; guess: string; key: string }
export interface Prag { kind: string; source: string; literal?: string; meaning?: string; why_it_matters?: string }
export interface GroundedSpan { source: string; rendered: string; node_id: string }
export interface LinkerSpan { type?: string; node_id?: string | null; method?: string; source?: string; start?: number }

/** One data message on topic "kin". Loose on purpose: each type uses a few of these fields. */
export interface KinMsg {
  type: string
  role?: Role
  text?: string
  items?: GlanceItem[]
  key?: string
  image_url?: string
  image_credit?: string
  source_url?: string
  body?: string
  speaker?: string
  listener?: string
  src_text?: string
  translation?: string
  target_lang?: string
  passthrough?: string[]
  grounded_spans?: GroundedSpan[]
  pragmatics_cards?: Prag[]
  linker_spans?: LinkerSpan[]
  utterance_id?: number
  present?: boolean
  person?: string
  asr?: string
  detail?: string
  stage?: string
  message?: string
}

const PICTURE_CATS = new Set(['food', 'festival', 'ritual', 'place', 'object'])
const CHIP: Record<string, string> = { saying: 'Saying', address: 'Address', idiom: 'Idiom', proverb: 'Saying', register: 'Address', honorific: 'Address', cultural: 'Culture' }
export const LIFETIME_MS: Record<Layout, number> = { info: 12000, compact: 9000, person: 9000, ask: Infinity }
export const ANSWERED_MS = 8000
export const SKELETON_MS = 6000 // no picture by then: the card settles as text-only
export const MAX_CARDS = 4
const DEDUPE_MS = 120000

export const norm = (s: unknown) => String(s ?? '').trim().toLowerCase()
const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : '')
const fresh = (seen: Map<string, number>, key: string, now: number) => now - (seen.get(key) ?? -Infinity) >= DEDUPE_MS
export const isHttps = (u?: string) => /^https:\/\//i.test(u || '')

export function layoutFor(it: GlanceItem): Layout {
  if (it.kind === 'who') return 'person'
  if (it.kind === 'ask') return 'ask'
  if (PICTURE_CATS.has(it.category || '') || ((it.kind === 'what' || it.kind === 'term') && it.image_url)) return 'info'
  return 'compact'
}

export function chipFor(it: GlanceItem): string {
  const layout = layoutFor(it)
  if (layout === 'person') return 'Who is this'
  if (layout === 'ask') return 'New relative'
  if (layout === 'info') return cap(it.category || '') || 'What is this'
  return CHIP[it.category || ''] || CHIP[it.kind] || (it.kind === 'what' ? 'What is this' : 'Culture')
}

const withLayout = (it: GlanceItem): Card => ({ ...it, layout: layoutFor(it), chip: chipFor(it) })

/** Cards and "Who is X?" asks for one glance event; deduped by item key (cards) and normalized kin term (asks). */
export function glanceCardsFor(items: GlanceItem[] | undefined, seen: Map<string, number>, asked: Set<string>, now: number) {
  const next = new Map(seen)
  const nextAsked = new Set(asked)
  const cards: Card[] = []
  const asks: Ask[] = []
  for (const it of items || []) {
    if (!it?.key) continue
    if (it.kind === 'ask') {
      const term = it.term || it.title || ''
      const key = norm(term)
      if (!key || nextAsked.has(key)) continue
      nextAsked.add(key)
      asks.push({ term, guess: it.guess || '', key })
      continue
    }
    if (!fresh(next, it.key, now)) continue
    next.set(it.key, now)
    next.set(`title:${norm(it.title)}`, now)
    cards.push(withLayout(it))
  }
  return { cards, asks, seen: next, asked: nextAsked }
}

/** A card after its glance_image follow-up: picture added, body only filled if it had none. */
export function mergeImage(it: Card, m: KinMsg): Card {
  return {
    ...withLayout({
      ...it,
      image_url: m.image_url || it.image_url || '',
      image_credit: m.image_credit || it.image_credit || '',
      source_url: m.source_url || it.source_url || '',
      body: it.body || m.body || '',
    }),
    literal: it.literal,
    why: it.why,
  }
}

/** Fallback cards from a transcript's grounded spans, plus idiom/culture cards (transcript or enrich). */
export function cardsFor(t: Pick<KinMsg, 'grounded_spans' | 'pragmatics_cards'>, seen: Map<string, number>, now: number) {
  const next = new Map(seen)
  const cards: Card[] = []
  for (const g of t.grounded_spans || []) {
    if (norm(g.rendered) === norm(g.source)) continue
    const isWho = String(g.node_id).startsWith('p_') // family-graph people are slugged p_*
    const key = isWho ? String(g.node_id) : `thing:${g.node_id}`
    if (!fresh(next, key, now) || !fresh(next, `title:${norm(g.source)}`, now)) continue
    next.set(key, now)
    next.set(`title:${norm(g.source)}`, now)
    cards.push(withLayout({ key, kind: isWho ? 'who' : 'what', title: g.source, body: g.rendered, category: '' }))
  }
  for (const c of t.pragmatics_cards || []) {
    const key = `card:${c.kind}:${c.source}`
    if (!fresh(next, key, now) || !fresh(next, `title:${norm(c.source)}`, now)) continue
    next.set(key, now)
    next.set(`title:${norm(c.source)}`, now)
    cards.push({ key, kind: c.kind, layout: 'compact', chip: CHIP[c.kind] || 'Culture', title: c.source, body: c.meaning, literal: c.literal, why: c.why_it_matters })
  }
  return { cards, seen: next }
}

/** Kin words the grandparent used that KIN could not place on the family graph: each becomes a "Who is X?" card. */
export function asksFor(t: Pick<KinMsg, 'linker_spans' | 'src_text'>, asked: Set<string>) {
  const next = new Set(asked)
  const asks: Ask[] = []
  for (const s of t.linker_spans || []) {
    if (s.type !== 'kin' || s.node_id || s.method !== 'unknown-relative') continue
    const key = norm(s.source)
    if (!key || next.has(key)) continue
    next.add(key)
    const before = (t.src_text || '').slice(0, s.start ?? 0).trim().split(/\s+/).pop() || ''
    asks.push({ term: s.source || '', guess: before.replace(/[.,!?;:"'“”‘’()]/g, ''), key })
  }
  return { asks, asked: next }
}

// ---- the rail: what is on screen, newest first --------------------------------
export interface RailEntry { id: string; at: number; card?: Card; ask?: Ask; answered?: string; answeredAt?: number }

const isOpenAsk = (e: RailEntry) => !!e.ask && e.answeredAt == null

/** Newest first; over the cap, the oldest info card goes first and unanswered questions go last. */
export function addToRail(rail: RailEntry[], added: RailEntry[], max = MAX_CARDS): RailEntry[] {
  const ids = new Set(added.map((e) => e.id))
  let next = [...[...added].reverse(), ...rail.filter((e) => !ids.has(e.id))]
  while (next.length > max) {
    const drop = next.findLastIndex((e) => !isOpenAsk(e))
    next = next.filter((_, i) => i !== (drop === -1 ? next.length - 1 : drop))
  }
  return next
}

export function expired(e: RailEntry, now: number): boolean {
  if (e.ask) return e.answeredAt != null && now - e.answeredAt >= ANSWERED_MS
  return now - e.at >= LIFETIME_MS[e.card!.layout]
}

export const pruneRail = (rail: RailEntry[], now: number) => {
  const next = rail.filter((e) => !expired(e, now))
  return next.length === rail.length ? rail : next
}
export const dismiss = (rail: RailEntry[], id: string) => rail.filter((e) => e.id !== id)
export const answerAsk = (rail: RailEntry[], id: string, answered: string, now: number) =>
  rail.map((e) => (e.id === id ? { ...e, answered, answeredAt: now } : e))
export const applyImage = (rail: RailEntry[], m: KinMsg) =>
  rail.map((e) => (e.card && e.card.key === m.key ? { ...e, card: mergeImage(e.card, m) } : e))

// ---- captions -------------------------------------------------------------------
export interface Part { text: string; pass: boolean }

/** The English line split so Fade passthrough words (kept in the heritage language) can be marked. */
export function passthroughParts(text: string, passthrough: string[] = []): Part[] {
  const pts = passthrough.filter(Boolean)
  if (!pts.length) return text ? [{ text, pass: false }] : []
  const re = new RegExp(`(${pts.map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g')
  return text.split(re).filter(Boolean).map((p) => ({ text: p, pass: pts.includes(p) }))
}

// ---- grandchild screen state ------------------------------------------------------
export interface Line { translation: string; src: string; passthrough: string[] }
export interface GcState { seen: Map<string, number>; asked: Set<string>; rail: RailEntry[]; line: Line | null; partial: string; status: string }

export const initialGc = (): GcState => ({ seen: new Map(), asked: new Set(), rail: [], line: null, partial: '', status: '' })

const cardEntries = (cards: Card[], now: number): RailEntry[] => cards.map((card) => ({ id: card.key, at: now, card }))
const askEntries = (asks: Ask[], now: number): RailEntry[] => asks.map((ask) => ({ id: `ask:${ask.key}`, at: now, ask }))

/** Folds one data message into the grandchild's screen. Messages about the grandchild's own speech are ignored. */
export function reduceGrandchild(s: GcState, m: KinMsg, now: number): GcState {
  switch (m.type) {
    case 'partial':
      return m.role === 'grandparent' ? { ...s, partial: m.text || '' } : s
    case 'glance': {
      if (m.role !== 'grandparent') return s
      const r = glanceCardsFor(m.items, s.seen, s.asked, now)
      return { ...s, seen: r.seen, asked: r.asked, rail: addToRail(s.rail, [...cardEntries(r.cards, now), ...askEntries(r.asks, now)]) }
    }
    case 'glance_image':
      return { ...s, rail: applyImage(s.rail, m) }
    case 'enrich': {
      const r = cardsFor({ pragmatics_cards: m.pragmatics_cards }, s.seen, now)
      return { ...s, seen: r.seen, rail: addToRail(s.rail, cardEntries(r.cards, now)) }
    }
    case 'transcript': {
      if (m.role !== 'grandparent') return s
      const c = cardsFor(m, s.seen, now) // anything the glance missed (same keys, so nothing shows twice)
      const q = asksFor(m, s.asked)
      return {
        ...s,
        seen: c.seen,
        asked: q.asked,
        partial: '',
        line: { translation: m.translation || '', src: m.src_text || '', passthrough: m.passthrough || [] },
        rail: addToRail(s.rail, [...cardEntries(c.cards, now), ...askEntries(q.asks, now)]),
      }
    }
    case 'status':
      return { ...s, status: m.asr === 'ok' ? '' : m.detail || '' }
    case 'error':
      return { ...s, status: `${m.stage || 'KIN'}: ${m.message || 'something went wrong'}` }
    default:
      return s
  }
}
