// One KIN call over LiveKit: connect, publish the mic, play the right tracks, duck the real voice under KIN's, and
// hand data messages (topic "kin") to the screen.
import { ConnectionState, RemoteAudioTrack, Room, RoomEvent, Track } from 'livekit-client'
import type { RemoteParticipant, RemoteTrack, RemoteTrackPublication } from 'livekit-client'
import type { JoinResult } from './api.ts'
import type { KinMsg } from './cards.ts'
import { AGENT_IDENTITY, lkUrl, routeTrack } from './routing.ts'

const DUCK_VOLUME = 0.25 // her real voice stays underneath KIN's
const DUCK_TAIL_MS = 700 // audio_end arrives when the last chunk is queued, a little before it is heard
const DUCK_MAX_MS = 30000 // a lost audio_end never leaves the voice ducked
const MIC = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }

export interface CallSnapshot { state: ConnectionState; peerName: string | null; canPlayAudio: boolean; muted: boolean; connectedAt: number }
type Listener = (m: KinMsg | null) => void // null: only the snapshot changed

export class KinCall {
  readonly room = new Room({ webAudioMix: true, audioCaptureDefaults: MIC }) // web audio: setVolume works on iOS
  join: JoinResult | null = null
  snap: CallSnapshot = { state: ConnectionState.Disconnected, peerName: null, canPlayAudio: true, muted: false, connectedAt: 0 }
  private listeners = new Set<Listener>()
  private queued: KinMsg[] = []
  private peerTracks = new Set<RemoteAudioTrack>()
  private ducked = false
  private duckTimer: ReturnType<typeof setTimeout> | undefined

  /** Call from the tap handler, before any await, so iOS lets the audio context start. */
  constructor() {
    this.room.startAudio().catch(() => this.update({ canPlayAudio: false }))
    const r = this.room
    r.on(RoomEvent.ConnectionStateChanged, (state) => this.update({ state }))
    r.on(RoomEvent.AudioPlaybackStatusChanged, () => this.update({ canPlayAudio: r.canPlaybackAudio }))
    r.on(RoomEvent.ParticipantConnected, () => this.refreshPeer())
    r.on(RoomEvent.ParticipantDisconnected, () => this.refreshPeer())
    r.on(RoomEvent.TrackPublished, (pub, p) => this.consider(pub, p))
    r.on(RoomEvent.TrackSubscribed, (track, pub, p) => this.play(track, pub, p))
    r.on(RoomEvent.TrackUnsubscribed, (track) => this.stop(track))
    r.on(RoomEvent.DataReceived, (payload, _p, _kind, topic) => this.onData(payload, topic))
    r.on(RoomEvent.Disconnected, () => { this.peerTracks.forEach((t) => this.stop(t)); this.update({ state: ConnectionState.Disconnected }) })
  }

  async connect(j: JoinResult): Promise<void> {
    this.join = j
    await this.room.connect(lkUrl(j.url, location.host, location.protocol), j.token, { autoSubscribe: false })
    this.update({ connectedAt: Date.now() })
    for (const p of this.room.remoteParticipants.values()) for (const pub of p.trackPublications.values()) this.consider(pub, p)
    this.refreshPeer()
    await this.room.localParticipant.setMicrophoneEnabled(true, MIC)
  }

  on(fn: Listener): () => void {
    this.listeners.add(fn)
    const q = this.queued
    this.queued = []
    q.forEach(fn) // messages that arrived before the screen was listening
    return () => this.listeners.delete(fn)
  }

  async setMuted(muted: boolean): Promise<void> {
    await this.room.localParticipant.setMicrophoneEnabled(!muted, MIC)
    this.update({ muted })
  }

  unlockAudio = () => this.room.startAudio().then(() => this.update({ canPlayAudio: this.room.canPlaybackAudio }))
  hangUp = () => this.room.disconnect()

  private emit(m: KinMsg | null) {
    if (m && !this.listeners.size) this.queued.push(m)
    this.listeners.forEach((fn) => fn(m))
  }
  private update(p: Partial<CallSnapshot>) { this.snap = { ...this.snap, ...p }; this.emit(null) }

  private refreshPeer() {
    const peer = [...this.room.remoteParticipants.values()].find((p) => p.identity !== AGENT_IDENTITY)
    this.update({ peerName: peer ? peer.name || peer.identity : null })
  }

  /** Subscribe only to audio this listener should hear (autoSubscribe is off). */
  private consider(pub: RemoteTrackPublication, p: RemoteParticipant) {
    if (pub.kind !== Track.Kind.Audio) return
    if (routeTrack(pub.trackName, p.identity, this.room.localParticipant.identity) !== 'skip') pub.setSubscribed(true)
  }

  private play(track: RemoteTrack, pub: RemoteTrackPublication, p: RemoteParticipant) {
    const route = routeTrack(pub.trackName, p.identity, this.room.localParticipant.identity)
    if (!(track instanceof RemoteAudioTrack) || route === 'skip') { pub.setSubscribed(false); return }
    const el = track.attach()
    el.hidden = true
    document.body.append(el)
    if (route === 'peer') {
      this.peerTracks.add(track)
      track.setVolume(this.ducked ? DUCK_VOLUME : 1)
    }
  }

  private stop(track: RemoteTrack) {
    track.detach().forEach((el) => el.remove())
    if (track instanceof RemoteAudioTrack) this.peerTracks.delete(track)
  }

  private duck(on: boolean, afterMs = 0) {
    clearTimeout(this.duckTimer)
    const apply = () => { this.ducked = on; this.peerTracks.forEach((t) => t.setVolume(on ? DUCK_VOLUME : 1)) }
    if (afterMs) this.duckTimer = setTimeout(apply, afterMs)
    else apply()
    if (on) this.duckTimer = setTimeout(() => this.duck(false), DUCK_MAX_MS)
  }

  private onData(payload: Uint8Array, topic?: string) {
    if (topic !== 'kin') return
    let m: KinMsg
    try { m = JSON.parse(new TextDecoder().decode(payload)) } catch { return }
    if (m.type === 'audio_start') this.duck(true)
    else if (m.type === 'audio_end') this.duck(false, DUCK_TAIL_MS)
    this.emit(m)
  }
}
