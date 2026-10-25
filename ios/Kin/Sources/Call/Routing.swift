/// Which remote tracks to subscribe to and how to play them. Pure.

let agentIdentity = "kin"  // backend/app/rtc/agent.py AGENT_IDENTITY

enum TrackKind: Sendable { case audio, video }

enum TrackRoute: Equatable, Sendable { case kinVoice, peerAudio, peerVideo, ignore }

/// The agent publishes one translated-voice track per listener, `kin-to-<identity>`: play only mine, never anyone
/// else's (that is their translation). A peer's own audio and video play normally. Anything else from the agent,
/// and any `kin-to-*` track not published by the agent, is ignored.
func routeTrack(name: String, participantIdentity: String, me: String, kind: TrackKind) -> TrackRoute {
    if participantIdentity == me { return .ignore }
    if name.hasPrefix("kin-to-") {
        return participantIdentity == agentIdentity && kind == .audio && name == "kin-to-\(me)" ? .kinVoice : .ignore
    }
    if participantIdentity == agentIdentity { return .ignore }
    return kind == .audio ? .peerAudio : .peerVideo
}

/// Only the agent (or the LiveKit server itself, sender nil) may speak on topic `kin`. Every participant token has
/// can_publish_data (backend/app/rtc/agent.py mint_token), so a peer could otherwise forge kin_status or cards.
func acceptsKinData(topic: String, sender: String?) -> Bool {
    topic == "kin" && (sender == nil || sender == agentIdentity)
}

/// Utterances whose KIN voice is playing for me. Peers are ducked while this is non-empty. A set, not a bool, so
/// overlapping utterances unduck only after the last audio_end.
func speakingUtterances(after msg: KinWorldMsg, voiceOn: Bool, current: Set<Int>) -> Set<Int> {
    switch msg {
    case .audioStart(let a): return voiceOn ? current.union([a.utteranceId]) : current
    case .audioEnd(let a): return current.subtracting([a.utteranceId])
    default: return current
    }
}

let duckedVolume = 0.25  // peers while KIN's voice for me plays

func peerVolume(kinSpeaking: Bool) -> Double { kinSpeaking ? duckedVolume : 1.0 }
