import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ANSWERED_MS, addToRail, answerAsk, applyImage, glanceCardsFor, initialGc, layoutFor, passthroughParts, pruneRail, reduceGrandchild } from '../src/cards.ts'
import type { KinMsg, RailEntry } from '../src/cards.ts'

const glance = (items: KinMsg['items'], role: 'grandparent' | 'grandchild' = 'grandparent'): KinMsg => ({ type: 'glance', role, items })

test('layout by kind and category', () => {
  assert.equal(layoutFor({ key: 'p_1', kind: 'who' }), 'person')
  assert.equal(layoutFor({ key: 'a', kind: 'ask' }), 'ask')
  assert.equal(layoutFor({ key: 't', kind: 'what', category: 'food' }), 'info')
  assert.equal(layoutFor({ key: 't', kind: 'term', image_url: 'https://x/y.jpg' }), 'info')
  assert.equal(layoutFor({ key: 's', kind: 'saying' }), 'compact')
})

test('glance cards dedupe by key, asks dedupe by term, and the grandchild own glance is ignored', () => {
  let s = reduceGrandchild(initialGc(), glance([{ key: 'thing:pongal', kind: 'what', title: 'Pongal', category: 'festival' }, { key: 'ask:ravi', kind: 'ask', term: 'Mama', guess: 'Ravi' }]), 0)
  s = reduceGrandchild(s, glance([{ key: 'thing:pongal', kind: 'what', title: 'Pongal' }, { key: 'ask:x', kind: 'ask', term: 'mama' }]), 1000)
  assert.deepEqual(s.rail.map((e) => e.id), ['ask:mama', 'thing:pongal'])
  assert.equal(reduceGrandchild(s, glance([{ key: 'new', kind: 'what', title: 'X' }], 'grandchild'), 2000), s)
  // a transcript grounded span for a term already on screen does not add a second card
  s = reduceGrandchild(s, { type: 'transcript', role: 'grandparent', translation: 'Happy Pongal', src_text: 'x', grounded_spans: [{ source: 'Pongal', rendered: 'the harvest festival', node_id: 'pongal2' }] }, 3000)
  assert.equal(s.rail.length, 2)
  assert.equal(s.line?.translation, 'Happy Pongal')
})

test('glance_image merges the picture and keeps the existing body', () => {
  const r = glanceCardsFor([{ key: 'thing:dosa', kind: 'what', title: 'Dosa', body: 'Rice crepe' }], new Map(), new Set(), 0)
  assert.equal(r.cards[0].layout, 'compact')
  const rail = applyImage(addToRail([], [{ id: 'thing:dosa', at: 0, card: r.cards[0] }]), { type: 'glance_image', key: 'thing:dosa', image_url: 'https://img/dosa.jpg', body: 'other' })
  assert.equal(rail[0].card?.image_url, 'https://img/dosa.jpg')
  assert.equal(rail[0].card?.body, 'Rice crepe')
  assert.equal(rail[0].card?.layout, 'info')
})

test('rail keeps 4, newest first, drops oldest info card before an open question', () => {
  const card = (id: string, at: number): RailEntry => ({ id, at, card: { key: id, kind: 'what', layout: 'compact', chip: 'x' } })
  let rail = addToRail([], [{ id: 'ask:a', at: 0, ask: { term: 'a', guess: '', key: 'a' } }])
  rail = addToRail(rail, [card('c1', 1), card('c2', 2), card('c3', 3)])
  rail = addToRail(rail, [card('c4', 4)])
  assert.deepEqual(rail.map((e) => e.id), ['c4', 'c3', 'c2', 'ask:a'])
})

test('cards expire by layout; open asks stay; answered asks leave after ANSWERED_MS', () => {
  let rail = addToRail([], [
    { id: 'c', at: 0, card: { key: 'c', kind: 'saying', layout: 'compact', chip: 'Saying' } },
    { id: 'ask:a', at: 0, ask: { term: 'a', guess: '', key: 'a' } },
  ])
  rail = pruneRail(rail, 10000)
  assert.deepEqual(rail.map((e) => e.id), ['ask:a'])
  rail = answerAsk(rail, 'ask:a', 'your uncle', 10000)
  assert.equal(pruneRail(rail, 10000 + ANSWERED_MS - 1).length, 1)
  assert.equal(pruneRail(rail, 10000 + ANSWERED_MS).length, 0)
})

test('transcript linker spans make a Who is X ask with the word before as the name', () => {
  const s = reduceGrandchild(initialGc(), { type: 'transcript', role: 'grandparent', src_text: 'Ravi mama called', linker_spans: [{ type: 'kin', node_id: null, method: 'unknown-relative', source: 'mama', start: 5 }] }, 0)
  assert.deepEqual(s.rail[0].ask, { term: 'mama', guess: 'Ravi', key: 'mama' })
})

test('partials show only for the grandparent and clear on transcript', () => {
  let s = reduceGrandchild(initialGc(), { type: 'partial', role: 'grandparent', text: 'enna' }, 0)
  assert.equal(s.partial, 'enna')
  assert.equal(reduceGrandchild(s, { type: 'partial', role: 'grandchild', text: 'hi' }, 0).partial, 'enna')
  s = reduceGrandchild(s, { type: 'transcript', role: 'grandparent', translation: 'what', src_text: 'enna' }, 1)
  assert.equal(s.partial, '')
})

test('passthrough words are marked', () => {
  assert.deepEqual(passthroughParts('Eat your rasam now', ['rasam']), [{ text: 'Eat your ', pass: false }, { text: 'rasam', pass: true }, { text: ' now', pass: false }])
  assert.deepEqual(passthroughParts('plain'), [{ text: 'plain', pass: false }])
})
