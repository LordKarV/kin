import { test } from 'node:test'
import assert from 'node:assert/strict'
import { lkUrl, routeTrack } from '../src/routing.ts'

test('play only my kin-to track, never the other listener one', () => {
  assert.equal(routeTrack('kin-to-grandchild-7', 'kin', 'grandchild-7'), 'kin')
  assert.equal(routeTrack('kin-to-grandparent-7', 'kin', 'grandchild-7'), 'skip')
  assert.equal(routeTrack('kin-to-grandparent-7', 'kin', 'grandparent-7'), 'kin')
  assert.equal(routeTrack('kin-to-grandchild-7', 'kin', 'grandparent-7'), 'skip')
})

test('the other person mic plays as the peer voice; other agent audio is skipped', () => {
  assert.equal(routeTrack('', 'grandparent-7', 'grandchild-7'), 'peer')
  assert.equal(routeTrack('microphone', 'grandchild-7', 'grandparent-7'), 'peer')
  assert.equal(routeTrack('something', 'kin', 'grandchild-7'), 'skip')
})

test('LiveKit URL: wss from the API as is, else this origin (proxied /rtc)', () => {
  assert.equal(lkUrl('wss://kin.livekit.cloud', '10.0.0.5:5174'), 'wss://kin.livekit.cloud')
  assert.equal(lkUrl('ws://localhost:7880', '10.0.0.5:5174'), 'wss://10.0.0.5:5174')
  assert.equal(lkUrl('ws://localhost:7880', 'localhost:5174', 'http:'), 'ws://localhost:5174')
})
