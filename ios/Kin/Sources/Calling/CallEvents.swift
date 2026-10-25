import Foundation

/// POST /api/calls/ring body and reply.
struct RingIn: Encodable, Equatable {
    let to: String  // the callee's person slug
    let video: Bool
}

struct RingOut: Decodable, Equatable {
    let callId: Int
    let delivered: Bool  // false: the callee's app is not open; the ring still waits 45 s in case they open it
    enum CodingKeys: String, CodingKey {
        case delivered
        case callId = "call_id"
    }
}

/// The other person on a ring.
struct RingPeer: Codable, Sendable, Equatable {
    let slug: String
    let name: String
}

/// One message from WS /ws/events (backend/app/api/events.py).
enum CallEvent: Sendable, Equatable {
    case incoming(callId: Int, from: RingPeer, video: Bool)
    case answered(callId: Int)
    case declined(callId: Int)
    case cancelled(callId: Int)
    case missed(callId: Int)
    case contacts  // contact.request | contact.accepted: People reloads its requests and contacts
    case ping

    private struct Wire: Decodable {
        let type: String
        let callId: Int?
        let from: RingPeer?
        let video: Bool?
        enum CodingKeys: String, CodingKey {
            case type, from, video
            case callId = "call_id"
        }
    }

    /// nil for anything this app does not know (newer servers may add types).
    static func decode(_ data: Data) -> CallEvent? {
        guard let w = try? JSONDecoder().decode(Wire.self, from: data) else { return nil }
        if w.type == "ping" { return .ping }
        if w.type == "contact.request" || w.type == "contact.accepted" { return .contacts }
        guard let id = w.callId else { return nil }
        switch w.type {
        case "call.incoming": return w.from.map { .incoming(callId: id, from: $0, video: w.video ?? true) }
        case "call.answered": return .answered(callId: id)
        case "call.declined": return .declined(callId: id)
        case "call.cancelled": return .cancelled(callId: id)
        case "call.missed": return .missed(callId: id)
        default: return nil
        }
    }
}
