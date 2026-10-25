import Foundation

struct ExplainIn: Encodable, Equatable {
    let text: String
    let utteranceId: Int?
    enum CodingKeys: String, CodingKey { case text; case utteranceId = "utterance_id" }

    // Always send utterance_id, as null when unknown (the route's body is {text, utterance_id: int | null}).
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(text, forKey: .text)
        try c.encode(utteranceId, forKey: .utteranceId)
    }
}

struct ExplainOut: Decodable, Equatable { let items: [GlanceItem] }

extension KinAPI {
    /// Tap-to-explain (ARCHITECTURE Amendment 5, backend/app/api/explain.py): `POST /api/calls/{id}/explain`.
    /// Returns a who/what/storyline/term card, a single "ask" item, or nothing when the text is not a name or term.
    func explain(callId: Int, text: String, utteranceId: Int?) async throws -> [GlanceItem] {
        let out: ExplainOut = try await request("POST", "/api/calls/\(callId)/explain",
                                                body: ExplainIn(text: text, utteranceId: utteranceId))
        return out.items
    }

    /// JSON request with the same headers, timeout and error mapping as KinAPI's own calls (whose plumbing is
    /// private to KinAPI.swift). Also used by the People, person-world and Messages screens.
    func request<Out: Decodable>(_ method: String, _ path: String, body: (any Encodable)? = nil) async throws -> Out {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw KinAPIError(status: nil, message: "Bad server address \(baseURL)")
        }
        var req = URLRequest(url: url, timeoutInterval: Self.timeout)
        req.httpMethod = method
        if let body {
            req.httpBody = try JSONEncoder().encode(body)
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if let token { req.setValue(token, forHTTPHeaderField: "X-KIN-User") }
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
        do { return try JSONDecoder().decode(Out.self, from: data) } catch {
            throw KinAPIError(status: nil, message: "Unexpected reply from KIN (\(path)): \(error)")
        }
    }
}
