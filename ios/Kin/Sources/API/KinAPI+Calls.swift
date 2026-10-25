import Foundation

/// Ringing (backend/app/api/calls.py): ring a contact, then the callee answers or declines and the caller can cancel.
/// Joining stays POST /api/rtc/join with the call id (both people already hold a seat).
extension KinAPI {
    func ring(to person: String, video: Bool) async throws -> RingOut {
        try await send("POST", "/api/calls/ring", RingIn(to: person, video: video))
    }
    func answer(callId: Int) async throws -> OkOut { try await send("POST", "/api/calls/\(callId)/answer") }
    func decline(callId: Int) async throws -> OkOut { try await send("POST", "/api/calls/\(callId)/decline") }
    func cancelRing(callId: Int) async throws -> OkOut { try await send("POST", "/api/calls/\(callId)/cancel") }
}
