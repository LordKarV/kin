import { test } from 'node:test'
import assert from 'node:assert/strict'
import { inviteLink, langLabel, parseInvite } from '../src/links.ts'

test('invite link round-trips', () => {
  const link = inviteLink('10.0.0.5:5174', 12, 3)
  assert.equal(link, 'https://10.0.0.5:5174/?call=12&family=3&role=grandparent')
  assert.deepEqual(parseInvite(new URL(link).search), { call: 12, family: 3, role: 'grandparent', key: '' })
  assert.equal(parseInvite(new URL(inviteLink('h', 1, 2, 'k1')).search)?.key, 'k1')
})

test('non-invite query strings parse to null', () => {
  assert.equal(parseInvite(''), null)
  assert.equal(parseInvite('?call=12&family=3&role=grandchild'), null)
  assert.equal(parseInvite('?call=abc&family=3&role=grandparent'), null)
  assert.equal(parseInvite('?family=3&role=grandparent'), null)
})

test('language label in its own language, falling back to the code', () => {
  assert.equal(langLabel('es'), 'español')
  assert.equal(langLabel('ta', 'en'), 'Tamil')
  assert.equal(langLabel('!!'), '!!')
})
