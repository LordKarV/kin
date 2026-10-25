import Foundation

/// Connect without a link (backend/app/api/connect.py): a KIN handle, requests to a handle, accept or decline.
struct HandleOut: Decodable, Equatable { let handle: String }
struct ConnectIn: Encodable { let handle: String }
/// status: "pending" (request sent) or "accepted" (they had already asked me, or we were connected).
struct ConnectOut: Decodable, Equatable {
    let status: String
    let user: RingPeer
}
struct ConnectRequestOut: Decodable, Equatable, Identifiable {
    let from: RingPeer
    let createdAt: String
    var id: String { from.slug }
    enum CodingKeys: String, CodingKey {
        case from
        case createdAt = "created_at"
    }
}
struct ConnectStatusOut: Decodable, Equatable { let status: String }
/// A request to a slug from POST /api/connect/match (a matched user may not have a handle yet).
struct ConnectSlugIn: Encodable { let slug: String }
struct ContactMatchIn: Encodable { let hashes: [String] }
/// relation: "none" | "requested" | "incoming" | "connected".
struct MatchedUser: Decodable, Equatable, Identifiable {
    let slug: String
    let name: String
    var relation: String
    var id: String { slug }
}
struct ContactMatchOut: Decodable, Equatable { let results: [MatchedUser] }

extension KinAPI {
    func myHandle() async throws -> HandleOut { try await send("GET", "/api/me/handle") }
    func connect(handle: String) async throws -> ConnectOut { try await send("POST", "/api/connect", ConnectIn(handle: handle)) }
    func connect(slug: String) async throws -> ConnectOut { try await send("POST", "/api/connect", ConnectSlugIn(slug: slug)) }
    func matchContacts(hashes: [String]) async throws -> [MatchedUser] {
        let out: ContactMatchOut = try await send("POST", "/api/connect/match", ContactMatchIn(hashes: hashes))
        return out.results
    }
    func connectRequests() async throws -> [ConnectRequestOut] { try await send("GET", "/api/connect/requests") }
    func answerRequest(from slug: String, accept: Bool) async throws -> ConnectStatusOut {
        let path = slug.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? slug
        return try await send("POST", "/api/connect/\(path)/\(accept ? "accept" : "decline")")
    }
}
