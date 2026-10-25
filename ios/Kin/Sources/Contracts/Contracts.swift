// Wire contracts for world calls (docs/ARCHITECTURE.md section 9). Mirrors backend/app/world/contracts.py;
// change both together. Foundation only.
//
// Decode server messages with `KinWorldMsg.decode(data)` or a plain JSONDecoder (default key strategy):
// snake_case keys are mapped with explicit CodingKeys, because convertFromSnakeCase would also rewrite the keys of
// `latencies` dictionaries ("mt_ms_zh" -> "mtMsZh").

import Foundation

// MARK: - Shared pieces

public struct Participant: Codable, Sendable, Equatable {
    public let identity: String
    public let person: String
    public let name: String
    public let lang: String
}

public struct PausedBy: Codable, Sendable, Equatable {
    public let person: String
    public let name: String
}

public struct KinState: Codable, Sendable, Equatable {
    public let on: Bool
    public let pausedBy: PausedBy?
    enum CodingKeys: String, CodingKey { case on; case pausedBy = "paused_by" }
}

public struct Suggestion: Codable, Sendable, Equatable {
    public let owner: String
    public let relation: String
    public let label: String
}

public struct StoryState: Codable, Sendable, Equatable {
    public let label: String
    public let at: String  // "YYYY-MM-DD"
    public let known: Bool

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        label = try c.decodeIfPresent(String.self, forKey: .label) ?? ""
        at = try c.decodeIfPresent(String.self, forKey: .at) ?? ""
        known = try c.decodeIfPresent(Bool.self, forKey: .known) ?? false
    }
}

// MARK: - GlanceItem (one card)

public struct GlanceItem: Codable, Sendable, Equatable, Identifiable {
    public var id: String { key }
    public let key: String      // who:<slug> | what:<slug> | bridge:<fact_id> | story:<id> | ask:<norm> | lex:<lang>:<k>
    public let kind: String     // who|what|term|saying|ask|bridge|storyline; unknown kinds are kept, render as generic
    public let title: String
    public let native: String
    public let body: String
    public let category: String
    public let imageUrl: String
    public let imageCredit: String
    public let sourceUrl: String
    public let nodeId: String?  // who/what
    public let gap: String?     // new|reminder
    public let term: String     // ask
    public let guess: String
    public let suggestions: [Suggestion]
    public let target: String?  // bridge: who has not heard it
    public let isPrivate: Bool
    public let storylineId: Int?
    public let states: [StoryState]

    enum CodingKeys: String, CodingKey {
        case key, kind, title, native, body, category, term, guess, suggestions, target, gap, states
        case imageUrl = "image_url", imageCredit = "image_credit", sourceUrl = "source_url", nodeId = "node_id"
        case isPrivate = "private", storylineId = "storyline_id"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func s(_ k: CodingKeys) throws -> String { try c.decodeIfPresent(String.self, forKey: k) ?? "" }
        key = try s(.key)
        kind = try s(.kind)
        title = try s(.title)
        native = try s(.native)
        body = try s(.body)
        category = try s(.category)
        imageUrl = try s(.imageUrl)
        imageCredit = try s(.imageCredit)
        sourceUrl = try s(.sourceUrl)
        nodeId = try c.decodeIfPresent(String.self, forKey: .nodeId)
        gap = try c.decodeIfPresent(String.self, forKey: .gap)
        term = try s(.term)
        guess = try s(.guess)
        suggestions = try c.decodeIfPresent([Suggestion].self, forKey: .suggestions) ?? []
        target = try c.decodeIfPresent(String.self, forKey: .target)
        isPrivate = try c.decodeIfPresent(Bool.self, forKey: .isPrivate) ?? false
        storylineId = try c.decodeIfPresent(Int.self, forKey: .storylineId)
        states = try c.decodeIfPresent([StoryState].self, forKey: .states) ?? []
    }
}

// MARK: - Server -> client messages (9.1)

public struct Joined: Codable, Sendable, Equatable {
    public let callId: Int
    public let identity: String
    public let person: String
    public let name: String
    public let lang: String
    public let role: String
    public let peerPresent: Bool
    public let participants: [Participant]
    public let kin: KinState
    enum CodingKeys: String, CodingKey {
        case identity, person, name, lang, role, participants, kin
        case callId = "call_id", peerPresent = "peer_present"
    }
}

public struct Participants: Codable, Sendable, Equatable { public let participants: [Participant] }

public struct KinStatus: Codable, Sendable, Equatable {
    public let on: Bool
    public let pausedBy: PausedBy?
    enum CodingKeys: String, CodingKey { case on; case pausedBy = "paused_by" }
}

public struct Partial: Codable, Sendable, Equatable {
    public let speaker: String  // identity
    public let person: String
    public let role: String
    public let lang: String
    public let text: String
    enum CodingKeys: String, CodingKey { case speaker, person, role, lang, text }
}

public struct Glance: Codable, Sendable, Equatable {
    public let speaker: String
    public let role: String
    public let partial: Bool
    public let items: [GlanceItem]
    enum CodingKeys: String, CodingKey { case speaker, role, partial, items }
}

public struct GlanceRetract: Codable, Sendable, Equatable { public let keys: [String] }

public struct GlanceUpdate: Codable, Sendable, Equatable {
    public let key: String
    public let body: String
}

public struct GroundedSpan: Codable, Sendable, Equatable {
    public let source: String
    public let rendered: String
    public let nodeId: String?  // nil when the node is not visible to this listener
    enum CodingKeys: String, CodingKey { case source, rendered; case nodeId = "node_id" }
}

public struct LinkerSpan: Codable, Sendable, Equatable {
    public let start: Int
    public let end: Int
    public let source: String
    public let nodeId: String?
    public let type: String
    public let confidence: Double
    public let rendered: String?
    public let candidates: [String]?
    public let method: String?
    enum CodingKeys: String, CodingKey {
        case start, end, source, type, confidence, rendered, candidates, method
        case nodeId = "node_id"
    }
}

public struct PragmaticsCard: Codable, Sendable, Equatable {
    public let kind: String?
    public let source: String?
    public let literal: String?
    public let meaning: String?
    public let whyItMatters: String?
    enum CodingKeys: String, CodingKey {
        case kind, source, literal, meaning
        case whyItMatters = "why_it_matters"
    }
}

public struct Transcript: Codable, Sendable, Equatable {
    public let callId: Int
    public let utteranceId: Int
    public let speaker: String  // person slug
    public let speakerIdentity: String
    public let role: String?
    public let listener: String?
    public let srcText: String
    public let srcLang: String
    public let targetLang: String
    public let translation: String?  // nil when the listener shares the speaker's language
    public let groundedSpans: [GroundedSpan]?
    public let pragmaticsCards: [PragmaticsCard]?
    public let confidence: Double?
    public let linkerSpans: [LinkerSpan]?
    public let latencies: [String: Double]?
    public let error: String?
    enum CodingKeys: String, CodingKey {
        case speaker, role, listener, translation, confidence, latencies, error
        case callId = "call_id", utteranceId = "utterance_id", speakerIdentity = "speaker_identity"
        case srcText = "src_text", srcLang = "src_lang", targetLang = "target_lang"
        case groundedSpans = "grounded_spans", pragmaticsCards = "pragmatics_cards", linkerSpans = "linker_spans"
    }
}

public struct Enrich: Codable, Sendable, Equatable {
    public let utteranceId: Int
    public let pragmaticsCards: [PragmaticsCard]
    public let bMs: Double?
    enum CodingKeys: String, CodingKey {
        case utteranceId = "utterance_id", pragmaticsCards = "pragmatics_cards", bMs = "b_ms"
    }
}

public struct AudioStart: Codable, Sendable, Equatable {
    public let utteranceId: Int
    public let lang: String
    enum CodingKeys: String, CodingKey { case lang; case utteranceId = "utterance_id" }
}

public struct AudioEnd: Codable, Sendable, Equatable {
    public let utteranceId: Int
    enum CodingKeys: String, CodingKey { case utteranceId = "utterance_id" }
}

public struct Latency: Codable, Sendable, Equatable {
    public let utteranceId: Int
    public let latencies: [String: Double]
    enum CodingKeys: String, CodingKey { case latencies; case utteranceId = "utterance_id" }
}

public struct Status: Codable, Sendable, Equatable {
    public let asr: String  // ok|unavailable|ended
    public let detail: String?
}

public struct ServerError: Codable, Sendable, Equatable {
    public let stage: String  // mt|tts|pipeline
    public let message: String?
}

// Python defaults these fields (contracts.py), and LiveWorld sends raw dicts, so a sender may omit them.
// Decoding with the same defaults keeps such a message from turning into `.unknown("malformed")`.
extension KeyedDecodingContainer {
    func decode<T: Decodable>(_ key: Key, or fallback: T) throws -> T { try decodeIfPresent(T.self, forKey: key) ?? fallback }
}

extension Joined {
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        callId = try c.decode(Int.self, forKey: .callId)
        identity = try c.decode(String.self, forKey: .identity)
        person = try c.decode(String.self, forKey: .person)
        name = try c.decode(String.self, forKey: .name)
        lang = try c.decode(String.self, forKey: .lang)
        role = try c.decode(.role, or: "participant")
        peerPresent = try c.decode(.peerPresent, or: false)
        participants = try c.decode(.participants, or: [Participant]())
        kin = try c.decode(KinState.self, forKey: .kin)
    }
}

extension Partial {
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        speaker = try c.decode(String.self, forKey: .speaker)
        person = try c.decode(String.self, forKey: .person)
        role = try c.decode(.role, or: "participant")
        lang = try c.decode(String.self, forKey: .lang)
        text = try c.decode(String.self, forKey: .text)
    }
}

extension Glance {
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        speaker = try c.decode(String.self, forKey: .speaker)
        role = try c.decode(.role, or: "participant")
        partial = try c.decode(.partial, or: false)
        items = try c.decode([GlanceItem].self, forKey: .items)
    }
}

extension Enrich {
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        utteranceId = try c.decode(Int.self, forKey: .utteranceId)
        pragmaticsCards = try c.decode(.pragmaticsCards, or: [PragmaticsCard]())
        bMs = try c.decodeIfPresent(Double.self, forKey: .bMs)
    }
}

/// One message on the LiveKit `kin` topic, decoded by its `type`. New server types decode to `.unknown`.
public enum KinWorldMsg: Decodable, Sendable, Equatable {
    case joined(Joined)
    case participants(Participants)
    case kinStatus(KinStatus)
    case partial(Partial)
    case glance(Glance)
    case glanceRetract(GlanceRetract)
    case glanceUpdate(GlanceUpdate)
    case transcript(Transcript)
    case enrich(Enrich)
    case audioStart(AudioStart)
    case audioEnd(AudioEnd)
    case latency(Latency)
    case status(Status)
    case error(ServerError)
    case unknown(String)

    private enum TypeKey: String, CodingKey { case type }

    public init(from decoder: Decoder) throws {
        let type = try decoder.container(keyedBy: TypeKey.self).decodeIfPresent(String.self, forKey: .type) ?? ""
        let one = try decoder.singleValueContainer()
        switch type {
        case "joined": self = .joined(try one.decode(Joined.self))
        case "participants": self = .participants(try one.decode(Participants.self))
        case "kin_status": self = .kinStatus(try one.decode(KinStatus.self))
        case "partial": self = .partial(try one.decode(Partial.self))
        case "glance": self = .glance(try one.decode(Glance.self))
        case "glance_retract": self = .glanceRetract(try one.decode(GlanceRetract.self))
        case "glance_update": self = .glanceUpdate(try one.decode(GlanceUpdate.self))
        case "transcript": self = .transcript(try one.decode(Transcript.self))
        case "enrich": self = .enrich(try one.decode(Enrich.self))
        case "audio_start": self = .audioStart(try one.decode(AudioStart.self))
        case "audio_end": self = .audioEnd(try one.decode(AudioEnd.self))
        case "latency": self = .latency(try one.decode(Latency.self))
        case "status": self = .status(try one.decode(Status.self))
        case "error": self = .error(try one.decode(ServerError.self))
        default: self = .unknown(type)
        }
    }

    /// Never throws: a malformed known message also becomes `.unknown`, so the app never crashes on server drift.
    public static func decode(_ data: Data) -> KinWorldMsg {
        (try? JSONDecoder().decode(KinWorldMsg.self, from: data)) ?? .unknown("malformed")
    }
}

// MARK: - REST bodies the app uses (9.2)

public struct UserIn: Codable, Sendable, Equatable {
    public let name: String
    public let lang: String
    public let phone: String?
    public init(name: String, lang: String, phone: String? = nil) { self.name = name; self.lang = lang; self.phone = phone }
}

public struct UserOut: Codable, Sendable, Equatable {
    public let userId: Int
    public let personId: Int
    public let person: String
    public let spaceId: Int
    public let token: String  // shown once; keep it in the Keychain
    public let smsNumber: String?
    enum CodingKeys: String, CodingKey {
        case person, token
        case userId = "user_id", personId = "person_id", spaceId = "space_id", smsNumber = "sms_number"
    }
}

public struct MeOut: Codable, Sendable, Equatable {
    public let userId: Int
    public let personId: Int
    public let person: String
    public let name: String
    public let lang: String
    public let phone: String?
    enum CodingKeys: String, CodingKey {
        case person, name, lang, phone
        case userId = "user_id", personId = "person_id"
    }
}

public struct ContactOut: Codable, Sendable, Equatable {
    public let person: String
    public let name: String
    public let lang: String
    public let render: String
    public let circle: String  // family|friends|group
}

public struct WorldPerson: Codable, Sendable, Equatable {
    public let id: Int
    public let person: String
    public let name: String
    public let render: String
    public let lang: String?
    public let isUser: Bool
    public let circle: String?
    enum CodingKeys: String, CodingKey { case id, person, name, render, lang, circle; case isUser = "is_user" }
}

public struct WorldTie: Codable, Sendable, Equatable {
    public let src: String
    public let dst: String
    public let kind: String
    public let context: String?
}

public struct WorldEdge: Codable, Sendable, Equatable {
    public let src: String
    public let dst: String
    public let relation: String
}

public struct WorldGroup: Codable, Sendable, Equatable {
    public let id: Int
    public let name: String
    public let members: [String]
}

public struct WorldThing: Codable, Sendable, Equatable {
    public let id: Int
    public let slug: String
    public let kind: String
    public let name: String
    public let owner: String?
}

public struct WorldStoryState: Codable, Sendable, Equatable {
    public let label: String
    public let at: String
}

public struct WorldStoryline: Codable, Sendable, Equatable {
    public let id: Int
    public let title: String
    public let status: String
    public let states: [WorldStoryState]
    public let owner: String?  // whose storyline (a person slug); absent from servers that predate it
    enum CodingKeys: String, CodingKey { case id, title, status, states, owner }
}

extension WorldStoryline {
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        title = try c.decode(String.self, forKey: .title)
        status = try c.decode(String.self, forKey: .status)
        states = try c.decode(.states, or: [WorldStoryState]())
        owner = try c.decodeIfPresent(String.self, forKey: .owner)
    }
}

public struct WorldOut: Codable, Sendable, Equatable {
    public let me: String  // my person slug
    public let people: [WorldPerson]
    public let ties: [WorldTie]
    public let edges: [WorldEdge]
    public let groups: [WorldGroup]
    public let things: [WorldThing]
    public let storylines: [WorldStoryline]
    enum CodingKeys: String, CodingKey { case me, people, ties, edges, groups, things, storylines }
}

extension WorldOut {
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        me = try c.decode(String.self, forKey: .me)
        people = try c.decode(.people, or: [WorldPerson]())
        ties = try c.decode(.ties, or: [WorldTie]())
        edges = try c.decode(.edges, or: [WorldEdge]())
        groups = try c.decode(.groups, or: [WorldGroup]())
        things = try c.decode(.things, or: [WorldThing]())
        storylines = try c.decode(.storylines, or: [WorldStoryline]())
    }
}

public struct PlaceIn: Codable, Sendable, Equatable {
    public let name: String?
    public let person: String?
    public let owner: String
    public let relation: String
    public let context: String?
    public let callId: Int?
    enum CodingKeys: String, CodingKey { case name, person, owner, relation, context; case callId = "call_id" }
    public init(name: String? = nil, person: String? = nil, owner: String, relation: String, context: String? = nil, callId: Int? = nil) {
        self.name = name; self.person = person; self.owner = owner; self.relation = relation
        self.context = context; self.callId = callId
    }
}

public struct PlaceOut: Codable, Sendable, Equatable {
    public let id: Int
    public let person: String
    public let name: String
    public let render: String
}

public struct JoinWorldIn: Codable, Sendable, Equatable {
    public let callId: Int?
    public let invite: String?  // the invite link's code: needed to take a new seat in an existing call
    enum CodingKeys: String, CodingKey { case invite; case callId = "call_id" }
    public init(callId: Int? = nil, invite: String? = nil) { self.callId = callId; self.invite = invite }
}

public struct JoinWorldOut: Codable, Sendable, Equatable {
    public let callId: Int
    public let room: String
    public let token: String
    public let url: String
    public let identity: String
    public let person: String
    public let name: String
    public let lang: String
    public let participants: [Participant]
    public let invite: String?  // this call's invite code, for the share link
    enum CodingKeys: String, CodingKey {
        case room, token, url, identity, person, name, lang, participants, invite
        case callId = "call_id"
    }
}

public struct PauseIn: Codable, Sendable, Equatable {
    public let paused: Bool
    public init(paused: Bool) { self.paused = paused }
}

public struct PauseOut: Codable, Sendable, Equatable {
    public let on: Bool
    public let pausedBy: PausedBy?
    enum CodingKeys: String, CodingKey { case on; case pausedBy = "paused_by" }
}

public struct FeedbackIn: Codable, Sendable, Equatable {
    public enum Action: String, Codable, Sendable { case know, dismiss, remember }
    public let key: String
    public let action: Action
    public init(key: String, action: Action) { self.key = key; self.action = action }
}

public struct TextIn: Codable, Sendable, Equatable {
    public let text: String
    public init(text: String) { self.text = text }
}

public struct OkOut: Codable, Sendable, Equatable { public let ok: Bool }
