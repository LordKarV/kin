import Foundation

/// The ring before a call: I am calling someone, someone is calling me, or my call was not answered. Pure: AppModel
/// applies `reduce` and runs the returned effect (REST call or LiveKit join).
enum RingState: Equatable, Sendable {
    case idle
    /// `callId` is nil until POST /api/calls/ring answers.
    case outgoing(callId: Int?, peer: RingPeer, video: Bool, delivered: Bool)
    case incoming(callId: Int, peer: RingPeer, video: Bool)
    /// Declined, missed or unreachable: the screen offers "Share invite instead".
    case unanswered(peer: RingPeer, video: Bool, message: String)
}

enum RingAction: Equatable, Sendable {
    case dial(RingPeer, video: Bool)
    case dialed(callId: Int, delivered: Bool)
    case dialFailed(String)
    case event(CallEvent)
    case cancel
    case answer
    case decline
    case dismiss
}

enum RingEffect: Equatable, Sendable {
    case join(callId: Int, video: Bool)  // my call was answered
    case answer(callId: Int, video: Bool)  // POST answer, then join
    case decline(Int)
    case cancel(Int)
}

extension RingState {
    /// The server's call id for a ring that has one.
    var callId: Int? {
        switch self {
        case .outgoing(let id, _, _, _): return id
        case .incoming(let id, _, _): return id
        case .idle, .unanswered: return nil
        }
    }

    /// The call id of a ring that has just got one (moving from `old` to this state), so AppModel can time it out.
    func startedRing(from old: RingState) -> Int? {
        guard let id = callId, id != old.callId else { return nil }
        return id
    }

    func reduce(_ action: RingAction) -> (RingState, RingEffect?) {
        switch (self, action) {
        case (.idle, .dial(let peer, let video)), (.unanswered, .dial(let peer, let video)):
            return (.outgoing(callId: nil, peer: peer, video: video, delivered: true), nil)
        case (.outgoing(nil, let peer, let video, _), .dialed(let id, let delivered)):
            return (.outgoing(callId: id, peer: peer, video: video, delivered: delivered), nil)
        case (_, .dialed(let id, _)):  // cancelled (or replaced by an incoming call) before the server answered
            return (self, .cancel(id))
        case (.outgoing(nil, let peer, let video, _), .dialFailed(let message)):
            return (.unanswered(peer: peer, video: video, message: message), nil)
        case (.outgoing(let id, _, _, _), .cancel):
            return (.idle, id.map { .cancel($0) })
        case (.incoming(let id, _, let video), .answer):
            return (.idle, .answer(callId: id, video: video))
        case (.incoming(let id, _, _), .decline):
            return (.idle, .decline(id))
        case (.unanswered, .dismiss), (.unanswered, .cancel):
            return (.idle, nil)
        case (_, .event(let event)):
            return on(event)
        default:
            return (self, nil)
        }
    }

    private func on(_ event: CallEvent) -> (RingState, RingEffect?) {
        switch (self, event) {
        case (.idle, .incoming(let id, let from, let video)), (.unanswered, .incoming(let id, let from, let video)):
            return (.incoming(callId: id, peer: from, video: video), nil)
        case (.incoming(let current, _, _), .incoming(let id, _, _)) where current == id:
            return (self, nil)  // replayed when the event socket reconnects
        case (_, .incoming(let id, _, _)):
            return (self, .decline(id))  // busy ringing someone else
        case (.outgoing(let current?, _, let video, _), .answered(let id)) where current == id:
            return (.idle, .join(callId: id, video: video))
        case (.outgoing(let current?, let peer, let video, _), .declined(let id)) where current == id:
            return (.unanswered(peer: peer, video: video, message: "\(peer.name) declined the call."), nil)
        case (.outgoing(let current?, let peer, let video, _), .missed(let id)) where current == id:
            return (.unanswered(peer: peer, video: video, message: "\(peer.name) didn't answer."), nil)
        case (.incoming(let current, _, _), .missed(let id)) where current == id,
             (.incoming(let current, _, _), .cancelled(let id)) where current == id:
            return (.idle, nil)
        default:
            return (self, nil)
        }
    }
}
