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
        let out: ExplainOut = try await send("POST", "/api/calls/\(callId)/explain",
                                             ExplainIn(text: text, utteranceId: utteranceId))
        return out.items
    }

    /// Existential-body wrapper over `send`, kept for the People, person-world and Messages screens (WorldModels).
    func request<Out: Decodable>(_ method: String, _ path: String, body: (any Encodable)? = nil) async throws -> Out {
        guard let body else { return try await send(method, path) }
        return try await send(method, path, body)  // SE-0352 opens the existential
    }
}
