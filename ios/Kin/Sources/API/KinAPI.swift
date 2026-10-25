import Foundation

/// GET /api/languages row (backend/app/api/languages.py). Only the fields the app reads.
struct LanguageOut: Codable, Sendable, Equatable, Identifiable {
    var id: String { code }
    let code: String
    let name: String
    let available: Bool?
}

struct KinAPIError: LocalizedError, Equatable {
    let status: Int?  // nil: transport or decoding failure
    let message: String
    var errorDescription: String? { message }

    /// The X-KIN-User token is missing or dead (signing in again fixes it). The KIN key gate also answers 401, but a
    /// wrong key must never cost the user their only token: both token 401s start with "X-KIN-User", the key's does not.
    var isBadToken: Bool { status == 401 && message.hasPrefix("X-KIN-User") }
}

/// DELETE /api/me reply (backend DeleteMeOut).
struct DeleteMeOut: Decodable, Equatable {
    let facts: Int
    let utterances: Int
}

/// Async URLSession client for the KIN backend (docs/ARCHITECTURE.md 9.2). Every call times out after 15 s.
/// The X-KIN-User token goes on every call except sign-up; the KIN key (from an invite) only when present.
struct KinAPI: Sendable {
    static let timeout: TimeInterval = 15
    let baseURL: URL
    let token: String?
    let apiKey: String?

    func signup(name: String, lang: String, phone: String?) async throws -> UserOut {
        try await send("POST", "/api/users", UserIn(name: name, lang: lang, phone: phone), auth: false)
    }
    func me() async throws -> MeOut { try await send("GET", "/api/me") }
    /// Deletes my account and everything KIN holds about me (PRODUCT: deleted means gone).
    func deleteMe() async throws -> DeleteMeOut { try await send("DELETE", "/api/me") }
    func contacts() async throws -> [ContactOut] { try await send("GET", "/api/contacts") }
    func world() async throws -> WorldOut { try await send("GET", "/api/world") }
    func place(_ body: PlaceIn) async throws -> PlaceOut { try await send("POST", "/api/world/place", body) }
    func joinWorld(callId: Int?, invite: String? = nil) async throws -> JoinWorldOut {
        try await send("POST", "/api/rtc/join", JoinWorldIn(callId: callId, invite: invite))
    }
    func pause(callId: Int, paused: Bool) async throws -> PauseOut {
        try await send("POST", "/api/calls/\(callId)/pause", PauseIn(paused: paused))
    }
    func feedback(callId: Int, key: String, action: FeedbackIn.Action) async throws -> OkOut {
        try await send("POST", "/api/calls/\(callId)/feedback", FeedbackIn(key: key, action: action))
    }
    func typeText(callId: Int, text: String) async throws -> OkOut {
        try await send("POST", "/api/calls/\(callId)/text", TextIn(text: text))
    }
    /// Amendment 2: per-call translated-voice toggle. The response shape is not in 9.2, so it is not decoded.
    func voice(callId: Int, on: Bool) async throws {
        _ = try await raw("POST", "/api/calls/\(callId)/voice", try JSONEncoder().encode(["on": on]), auth: true)
    }
    func languages() async throws -> [LanguageOut] { try await send("GET", "/api/languages", auth: false) }

    // MARK: - plumbing

    private struct Empty: Encodable {}

    func send<Out: Decodable>(_ method: String, _ path: String, auth: Bool = true) async throws -> Out {
        try await send(method, path, Empty?.none, auth: auth)
    }

    func send<In: Encodable, Out: Decodable>(_ method: String, _ path: String, _ body: In?,
                                                     auth: Bool = true) async throws -> Out {
        let data = try await raw(method, path, try body.map { try JSONEncoder().encode($0) }, auth: auth)
        do { return try JSONDecoder().decode(Out.self, from: data) } catch {
            throw KinAPIError(status: nil, message: "Unexpected reply from KIN (\(path)): \(error)")
        }
    }

    private func raw(_ method: String, _ path: String, _ body: Data?, auth: Bool) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw KinAPIError(status: nil, message: "Bad server address \(baseURL)")
        }
        var req = URLRequest(url: url, timeoutInterval: Self.timeout)
        req.httpMethod = method
        if let body { req.httpBody = body; req.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if auth, let token { req.setValue(token, forHTTPHeaderField: "X-KIN-User") }
        if let apiKey, !apiKey.isEmpty { req.setValue(apiKey, forHTTPHeaderField: "X-KIN-Key") }
        let (data, resp): (Data, URLResponse)
        do { (data, resp) = try await URLSession.shared.data(for: req) } catch let e as URLError where e.code == .timedOut {
            throw KinAPIError(status: nil, message: "KIN did not answer in time")
        } catch {
            throw KinAPIError(status: nil, message: "Could not reach KIN: \(error.localizedDescription)")
        }
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            throw KinAPIError(status: status, message: Self.detail(data) ?? "HTTP \(status)")
        }
        return data
    }

    /// FastAPI errors: {"detail": "text"} or {"detail": [{"msg": ...}]}.
    static func detail(_ data: Data) -> String? {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        if let s = obj["detail"] as? String { return s }
        if let arr = obj["detail"] as? [[String: Any]] {
            return arr.compactMap { $0["msg"] as? String }.joined(separator: "; ")
        }
        return nil
    }
}
