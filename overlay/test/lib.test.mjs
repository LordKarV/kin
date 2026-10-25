import assert from 'node:assert/strict'
import { test } from 'node:test'
import { cardsFor, esc, makeChunker, speakerChoices, translationHtml } from '../src/lib.mjs'

test('translationHtml marks passthrough words and escapes the rest', () => {
  const html = translationHtml({ translation: 'Did you eat <saapadu>? saapadu is ready', passthrough: ['saapadu'] })
  assert.equal(html, 'Did you eat &lt;<mark class="pass">saapadu</mark>&gt;? <mark class="pass">saapadu</mark> is ready')
  assert.equal(translationHtml({ translation: 'a & b' }), 'a &amp; b')
  assert.equal(esc('"x"'), '&quot;x&quot;')
})

test('cardsFor shows a person once per ttl and never mutates seen', () => {
  const t = {
    grounded_spans: [{ source: 'Ravi', rendered: "your uncle Ravi mama (Mom's younger brother)", node_id: 'p_ravi_mama' }],
    pragmatics_cards: [{ kind: 'idiom', source: 'x', literal: 'l', meaning: 'm', why_it_matters: 'w' }],
  }
  const seen0 = new Map()
  const a = cardsFor(t, seen0, 1000)
  assert.equal(a.cards.length, 2)
  assert.equal(seen0.size, 0)
  assert.equal(cardsFor(t, a.seen, 2000).cards.length, 0)
  assert.equal(cardsFor(t, a.seen, 1000 + 120000).cards.length, 2)
})

test('cardsFor labels places/dishes as "what" and skips renderings that add nothing', () => {
  const t = { grounded_spans: [
    { source: 'Adyar', rendered: "Ravi mama's flat in Adyar", node_id: 'adyar_flat' },
    { source: 'pongal', rendered: 'Pongal', node_id: 'pongal' },
  ] }
  const { cards } = cardsFor(t, new Map(), 0)
  assert.deepEqual(cards.map((c) => [c.kind, c.title]), [['what', 'Adyar']])
})

test('makeChunker emits fixed frames and keeps the remainder', () => {
  const frames = []
  const push = makeChunker(4, (f) => frames.push([...f]))
  push(Buffer.from([1, 2, 3]))
  push(Buffer.from([4, 5, 6, 7, 8, 9]))
  assert.deepEqual(frames, [[1, 2, 3, 4], [5, 6, 7, 8]])
})

test('speakerChoices drops the learner and the deceased, oldest first', () => {
  const g = { people: [
    { id: 'p_amma', name: 'Amma', generation: -1 },
    { id: 'p_arjun', name: 'Arjun', is_learner: true, generation: 0 },
    { id: 'p_kamala', name: 'Kamala', render: 'your grandmother', generation: -2 },
    { id: 'p_thatha', name: 'Thatha', deceased: true, generation: -2 },
  ] }
  assert.deepEqual(speakerChoices(g).map((p) => p.id), ['p_kamala', 'p_amma'])
})

test('asksFor: unplaced kin words become "Who is X?" questions, once each, with the name before them', async () => {
  const { asksFor } = await import('../src/lib.mjs')
  const t = { src_text: 'ரவி மாமா நேத்து போன் பண்ணான், Kamala paatti happy', linker_spans: [
    { start: 4, end: 8, source: 'மாமா', type: 'kin', node_id: null, method: 'unknown-relative' },
    { start: 0, end: 3, source: 'kanna', type: 'kin', node_id: null, method: 'generic-address' },  // endearment: no question
    { start: 43, end: 49, source: 'paatti', type: 'kin', node_id: 'p_kamala' },  // already known: no question
  ] }
  const a = asksFor(t, new Set())
  assert.deepEqual(a.asks, [{ term: 'மாமா', guess: 'ரவி', key: 'மாமா' }])
  assert.equal(asksFor(t, a.asked).asks.length, 0)  // never ask twice about the same word
})

const glance = (o) => ({ key: 'k', kind: 'term', title: 't', native: '', body: '', category: 'other', image_url: '', image_credit: '', source_url: '', ...o })

test('layoutFor / chipFor: picture bubble for things, compact for sayings, avatar for people', async () => {
  const { layoutFor, chipFor } = await import('../src/lib.mjs')
  assert.equal(layoutFor(glance({ kind: 'what', category: 'food' })), 'info')
  assert.equal(chipFor(glance({ kind: 'what', category: 'food' })), 'Food')
  assert.equal(layoutFor(glance({ kind: 'term', category: 'other', image_url: 'https://x/y.jpg' })), 'info')
  assert.equal(layoutFor(glance({ kind: 'saying', category: 'saying' })), 'compact')
  assert.equal(chipFor(glance({ kind: 'saying', category: 'saying' })), 'Saying')
  assert.equal(chipFor(glance({ kind: 'term', category: 'address' })), 'Address')
  assert.equal(layoutFor(glance({ kind: 'who', category: 'person' })), 'person')
  assert.equal(layoutFor(glance({ kind: 'ask' })), 'ask')
})

test('glanceCardsFor dedupes by key, routes asks through the asked set, never mutates state', async () => {
  const { glanceCardsFor } = await import('../src/lib.mjs')
  const items = [
    glance({ key: 'thing:pongal', kind: 'what', title: 'pongal', category: 'festival' }),
    glance({ key: 'ask:மாமா', kind: 'ask', title: 'மாமா', term: 'மாமா', guess: 'ரவி' }),
  ]
  const seen0 = new Map(), asked0 = new Set()
  const a = glanceCardsFor(items, seen0, asked0, 1000)
  assert.deepEqual(a.cards.map((c) => [c.key, c.layout, c.chip]), [['thing:pongal', 'info', 'Festival']])
  assert.deepEqual(a.asks, [{ term: 'மாமா', guess: 'ரவி', key: 'மாமா' }])
  assert.equal(seen0.size + asked0.size, 0)
  const b = glanceCardsFor(items, a.seen, a.asked, 2000)
  assert.equal(b.cards.length + b.asks.length, 0)
})

test('transcript fallback and enrich cards skip what a glance already showed', async () => {
  const { glanceCardsFor, asksFor } = await import('../src/lib.mjs')
  const g = glanceCardsFor([
    glance({ key: 'p_ravi', kind: 'who', title: 'Ravi', category: 'person' }),
    glance({ key: 'lex:ta:kanna', kind: 'saying', title: 'kanna', category: 'address' }),
    glance({ key: 'ask:மாமா', kind: 'ask', term: 'மாமா' }),
  ], new Map(), new Set(), 0)
  const t = {
    src_text: 'மாமா', linker_spans: [{ start: 0, end: 4, source: 'மாமா', type: 'kin', node_id: null, method: 'unknown-relative' }],
    grounded_spans: [{ source: 'Ravi', rendered: 'your uncle Ravi', node_id: 'p_ravi' }, { source: 'Adyar', rendered: 'the flat in Adyar', node_id: 'adyar' }],
    pragmatics_cards: [{ kind: 'honorific', source: 'Kanna', meaning: 'dear one' }, { kind: 'idiom', source: 'x', meaning: 'm' }],
  }
  const r = cardsFor(t, g.seen, 10)
  assert.deepEqual(r.cards.map((c) => [c.key, c.layout, c.chip]), [['thing:adyar', 'compact', 'What is this'], ['card:idiom:x', 'compact', 'Idiom']])
  assert.equal(asksFor(t, g.asked).asks.length, 0)
})

test('mergeImage adds the picture, keeps an existing body, fills a missing one, upgrades the layout', async () => {
  const { mergeImage } = await import('../src/lib.mjs')
  const m = { key: 'k', image_url: 'https://img/a.jpg', image_credit: 'CC BY-SA', source_url: 'https://en.wikipedia.org/wiki/A', body: 'From wiki' }
  const a = mergeImage({ ...glance({ kind: 'term', body: 'mine' }), layout: 'compact' }, m)
  assert.equal(a.body, 'mine')
  assert.equal(a.layout, 'info')
  assert.equal(a.image_credit, 'CC BY-SA')
  assert.equal(mergeImage(glance({}), m).body, 'From wiki')
})

test('markTerms underlines heard terms case-insensitively and escapes the rest', async () => {
  const { markTerms } = await import('../src/lib.mjs')
  assert.equal(markTerms('Pongal <today> pongal', ['pongal']), '<span class="heard">Pongal</span> &lt;today&gt; <span class="heard">pongal</span>')
  assert.equal(markTerms('a & b', []), 'a &amp; b')
})
