import AVFoundation
import Combine
import Foundation
import LiveKit

/// One video tile: plain values plus the track to render (nil shows the name only).
struct Tile: Identifiable {
    let id: String  // participant identity
    let name: String
    let track: VideoTrack?
}

/// Whether a routed peer video track becomes the tile's video: a live camera wins, any other live video fills in.
/// A muted track never shows: LiveKit mutes (does not unpublish) on camera off, so the track stays subscribed and
/// would freeze on its last frame instead of falling back to the avatar.
func showsPeerVideo(route: TrackRoute, isCamera: Bool, isMuted: Bool, haveVideo: Bool) -> Bool {
    route == .peerVideo && !isMuted && (isCamera || !haveVideo)
}

/// The LiveKit side of a world call. The call screen (task 4B) reads `participants`, `peers`, `selfTile`, the state
/// flags and `messages()`, and calls the toggles and `hangUp()`.
@MainActor
final class CallController: ObservableObject {
    let join: JoinWorldOut
    var callId: Int { join.callId }
    var me: String { join.identity }

    @Published private(set) var participants: [Participant]
    @Published private(set) var peers: [Tile] = []
    @Published private(set) var selfTile: Tile?
    @Published private(set) var isConnected = false
    @Published private(set) var isPaused = false
    @Published private(set) var pausedBy: PausedBy?
    @Published private(set) var micOn = true
    @Published private(set) var cameraOn = true
    @Published private(set) var voiceOn = false  // amendment 2: captions by default
    @Published private(set) var kinSpeaking = false
    /// The call banner's error, cleared by the next success or after `errorLifetime` (see `fail`).
    @Published private(set) var lastError: String?

    /// Subscribers to `messages()`, keyed so each stream can remove itself when its task is cancelled.
    private var sinks: [UUID: AsyncStream<KinWorldMsg>.Continuation] = [:]
    private var speaking: Set<Int> = []  // utterances whose KIN voice is playing for me
    private var subscribing: Set<String> = []  // publication sids with a subscribe request in flight

    private let api: KinAPI
    private let room = Room()
    private var events: RoomEvents?
    private let onEnded: @MainActor (Int) -> Void
    private let onFailed: @MainActor (String) -> Void
    private var ended = false
    private let errorLifetime: Duration
    private var errorExpiry: Task<Void, Never>?

    /// `onEnded(callId)` after a joined call ends; `onFailed(message)` when the room never connected.
    init(api: KinAPI, join: JoinWorldOut, errorLifetime: Duration = .seconds(6),
         onEnded: @escaping @MainActor (Int) -> Void, onFailed: @escaping @MainActor (String) -> Void) {
        self.api = api
        self.join = join
        self.errorLifetime = errorLifetime
        self.onEnded = onEnded
        self.onFailed = onFailed
        participants = join.participants
    }

    /// A fresh stream of every decoded `kin` message from now on, in order. Call it once per consumer, for example
    /// in a SwiftUI `.task`: a cancelled task ends only its own stream, and a restarted view just asks again
    /// (messages sent while it was gone are not replayed). Ends when the call ends.
    func messages() -> AsyncStream<KinWorldMsg> {
        let (stream, sink) = AsyncStream.makeStream(of: KinWorldMsg.self, bufferingPolicy: .bufferingNewest(500))
        guard !ended else { sink.finish(); return stream }
        let id = UUID()
        sinks[id] = sink
        sink.onTermination = { [weak self] _ in Task { @MainActor in self?.sinks[id] = nil } }
        return stream
    }

    /// Set just before AppModel.startCall() for an audio call, so the camera is never published. Known limit: a
    /// one-shot flag because AppModel.startCall has no camera parameter; thread `camera:` through it instead.
    static var audioOnlyNext = false

    func connect() async {
        let camera = !Self.audioOnlyNext
        Self.audioOnlyNext = false
        // Voice chat mode turns on iOS echo cancellation, which a speakerphone call needs.
        AudioManager.shared.sessionConfiguration = AudioSessionConfiguration(
            category: .playAndRecord, categoryOptions: [.defaultToSpeaker], mode: .voiceChat)
        let events = RoomEvents(
            onChange: { [weak self] in Task { @MainActor in self?.sync() } },
            onData: { [weak self] data in Task { @MainActor in self?.receive(data) } },
            onDisconnect: { [weak self] in Task { @MainActor in self?.finish() } })
        self.events = events
        room.add(delegate: events)
        do {
            try await room.connect(url: join.url, token: join.token, connectOptions: ConnectOptions(autoSubscribe: false))
            isConnected = true
        } catch {
            room.remove(delegate: events)
            self.events = nil
            close()
            onFailed("Could not join the call: \(error.localizedDescription)")
            return
        }
        do { try await room.localParticipant.setMicrophone(enabled: true) } catch {
            micOn = false
            fail("Microphone unavailable: \(error.localizedDescription)")
        }
        if !camera {
            cameraOn = false
        } else {
            do { try await room.localParticipant.setCamera(enabled: true) } catch {
                cameraOn = false  // the audio call works without video
                fail("Camera unavailable: \(error.localizedDescription)")
            }
        }
        sync()
    }

    func setMic(_ on: Bool) async {
        do { try await room.localParticipant.setMicrophone(enabled: on); micOn = on; lastError = nil } catch {
            fail("Microphone: \(error.localizedDescription)")
        }
    }

    func setCamera(_ on: Bool) async {
        do { try await room.localParticipant.setCamera(enabled: on); cameraOn = on; lastError = nil } catch {
            fail("Camera: \(error.localizedDescription)")
        }
        sync()
    }

    func setPaused(_ paused: Bool) async {
        do {
            let out = try await api.pause(callId: callId, paused: paused)
            isPaused = !out.on
            pausedBy = out.pausedBy
            lastError = nil
        } catch { fail("Pause: \(error.localizedDescription)") }
    }

    func setVoice(_ on: Bool) async {
        do {
            try await api.voice(callId: callId, on: on)
            voiceOn = on
            if !on { setSpeaking([]) }
            lastError = nil
        } catch { fail("Voice: \(error.localizedDescription)") }
    }

    func feedback(key: String, action: FeedbackIn.Action) async {
        do { _ = try await api.feedback(callId: callId, key: key, action: action); lastError = nil } catch {
            fail("Feedback: \(error.localizedDescription)")
        }
    }

    func typeText(_ text: String) async {
        do { _ = try await api.typeText(callId: callId, text: text); lastError = nil } catch {
            fail("Send: \(error.localizedDescription)")
        }
    }

    func place(_ body: PlaceIn) async throws -> PlaceOut { try await api.place(body) }

    /// Tap-to-explain: the card for a caption word, private to me.
    func explain(_ text: String, utteranceId: Int?) async throws -> [GlanceItem] {
        try await api.explain(callId: callId, text: text, utteranceId: utteranceId)
    }

    /// Double twist: the card for whatever the last lines I heard are about, private to me.
    func explainRecent() async throws -> [GlanceItem] { try await api.explainRecent(callId: callId) }

    func hangUp() async {
        await room.disconnect()
        finish()
    }

    // MARK: - events

    private func receive(_ data: Data) {
        let msg = KinWorldMsg.decode(data)
        switch msg {
        case .joined(let j):
            participants = j.participants
            isPaused = !j.kin.on
            pausedBy = j.kin.pausedBy
        case .participants(let p): participants = p.participants
        case .kinStatus(let s):
            isPaused = !s.on
            pausedBy = s.pausedBy
        case .audioStart, .audioEnd: setSpeaking(speakingUtterances(after: msg, voiceOn: voiceOn, current: speaking))
        case .unknown(let t): print("kin: ignored data message \(t)")
        default: break
        }
        for sink in sinks.values { sink.yield(msg) }
    }

    private func setSpeaking(_ next: Set<Int>) {
        speaking = next
        kinSpeaking = !next.isEmpty
        applyVolumes()
    }

    /// Subscribe to routed tracks, rebuild tiles and apply volumes from the room's current state.
    private func sync() {
        guard !ended else { return }
        var tiles: [Tile] = []
        var hasKinVoice = false
        for (_, p) in room.remoteParticipants {
            let identity = p.identity?.stringValue ?? ""
            var video: VideoTrack?
            for case let pub as RemoteTrackPublication in p.trackPublications.values {
                let kind: TrackKind? = pub.kind == .audio ? .audio : pub.kind == .video ? .video : nil
                guard let kind else { continue }
                let route = routeTrack(name: pub.name, participantIdentity: identity, me: me, kind: kind)
                guard route != .ignore else { continue }
                if route == .kinVoice { hasKinVoice = true }
                subscribe(pub)
                if showsPeerVideo(route: route, isCamera: pub.source == .camera, isMuted: pub.isMuted, haveVideo: video != nil),
                   let t = pub.track as? VideoTrack {
                    video = t
                }
            }
            if identity != agentIdentity {  // the agent is not a person on screen
                tiles.append(Tile(id: identity, name: displayName(identity, p.name), track: video))
            }
        }
        peers = tiles.sorted { $0.id < $1.id }
        let local = room.localParticipant.firstCameraPublication?.track as? VideoTrack
        selfTile = Tile(id: me, name: join.name, track: cameraOn ? local : nil)
        if !hasKinVoice && !speaking.isEmpty { setSpeaking([]) }  // my voice track is gone, so a lost audio_end can't keep peers ducked
        applyVolumes()
    }

    /// Requests each routed publication once; a failure is shown, and the next sync retries it.
    private func subscribe(_ pub: RemoteTrackPublication) {
        let sid = pub.sid.stringValue
        guard !pub.isSubscribed, !subscribing.contains(sid) else { return }
        subscribing.insert(sid)
        Task { @MainActor in
            defer { subscribing.remove(sid) }
            do { try await pub.set(subscribed: true) } catch {
                fail("Could not play \(pub.name.isEmpty ? "a track" : pub.name): \(error.localizedDescription)")
            }
        }
    }

    /// Shows `message` in the call banner for `errorLifetime`. CallView shows `lastError ?? world.error`, so an error
    /// that stayed would hide every later one (the simulator fails the camera on every connect).
    private func fail(_ message: String) {
        lastError = message
        errorExpiry?.cancel()
        errorExpiry = Task { [weak self, errorLifetime] in
            try? await Task.sleep(for: errorLifetime)  // throws only when a newer error cancelled this one
            guard !Task.isCancelled else { return }
            self?.lastError = nil
        }
    }

    private func applyVolumes() {
        let volume = peerVolume(kinSpeaking: kinSpeaking)
        for (_, p) in room.remoteParticipants {
            let identity = p.identity?.stringValue ?? ""
            for pub in p.audioTracks {
                guard let track = pub.track as? RemoteAudioTrack else { continue }
                switch routeTrack(name: pub.name, participantIdentity: identity, me: me, kind: .audio) {
                case .peerAudio: if track.volume != volume { track.volume = volume }
                case .kinVoice: if track.volume != 1.0 { track.volume = 1.0 }
                default: break
                }
            }
        }
    }

    private func displayName(_ identity: String, _ lkName: String?) -> String {
        participants.first { $0.identity == identity }?.name ?? lkName.flatMap { $0.isEmpty ? nil : $0 } ?? identity
    }

    private func finish() {
        guard !ended else { return }
        close()
        onEnded(callId)
    }

    private func close() {
        ended = true
        isConnected = false
        for sink in sinks.values { sink.finish() }
        sinks = [:]
    }
}

/// LiveKit calls delegates off the main thread; this forwards the events the controller needs as closures. Internal
/// only so a test can check that LiveKit sees each optional requirement.
final class RoomEvents: NSObject, RoomDelegate, Sendable {
    let onChange: @Sendable () -> Void
    let onData: @Sendable (Data) -> Void
    let onDisconnect: @Sendable () -> Void

    init(onChange: @escaping @Sendable () -> Void, onData: @escaping @Sendable (Data) -> Void,
         onDisconnect: @escaping @Sendable () -> Void) {
        self.onChange = onChange
        self.onData = onData
        self.onDisconnect = onDisconnect
    }

    func room(_ room: Room, participantDidConnect participant: RemoteParticipant) { onChange() }
    func room(_ room: Room, participantDidDisconnect participant: RemoteParticipant) { onChange() }
    func room(_ room: Room, participant: RemoteParticipant, didPublishTrack publication: RemoteTrackPublication) { onChange() }
    func room(_ room: Room, participant: RemoteParticipant, didUnpublishTrack publication: RemoteTrackPublication) { onChange() }
    func room(_ room: Room, participant: RemoteParticipant, didSubscribeTrack publication: RemoteTrackPublication) { onChange() }
    func room(_ room: Room, participant: RemoteParticipant, didUnsubscribeTrack publication: RemoteTrackPublication) { onChange() }
    func room(_ room: Room, participant: LocalParticipant, didPublishTrack publication: LocalTrackPublication) { onChange() }
    func room(_ room: Room, participant: LocalParticipant, didUnpublishTrack publication: LocalTrackPublication) { onChange() }
    // Camera off mutes the track rather than unpublishing it, so the tile has to re-sync to show the avatar.
    func room(_ room: Room, participant: LiveKit.Participant, trackPublication: TrackPublication,
              didUpdateIsMuted isMuted: Bool) {
        onChange()
    }
    func room(_ room: Room, didDisconnectWithError error: LiveKitError?) { onDisconnect() }
    func room(_ room: Room, participant: RemoteParticipant?, didReceiveData data: Data, forTopic topic: String,
              encryptionType: EncryptionType) {
        if acceptsKinData(topic: topic, sender: participant?.identity?.stringValue) { onData(data) }
    }
}
