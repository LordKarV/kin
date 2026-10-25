import Foundation

/// POST /api/me/messages body and reply (backend/app/api/messages.py): typing news to KIN in the app takes the same
/// path as texting KIN's number. `facts` are the FactRows the message created (GET /api/me/facts shape).
struct MessageIn: Encodable { let text: String }
struct MessageOut: Decodable, Equatable {
    let reply: String
    let facts: [FactRow]
}

extension KinAPI {
    func sendMessage(_ text: String) async throws -> MessageOut { try await send("POST", "/api/me/messages", MessageIn(text: text)) }
}

/// The Messages thread: my texts (blue, right) and KIN's replies (grey, left). Known limit: this session only. The server
/// clears a message's text once it is parsed (privacy), so there is no history to load; "What KIN understood" is the
/// durable record.
struct MessageThread: Equatable {
    struct Bubble: Equatable, Identifiable {
        let id: Int
        let text: String
        let mine: Bool
    }

    static let maxLength = 500  // MessageIn on the server

    private(set) var bubbles: [Bubble] = []
    private(set) var error: String?

    /// Sends `draft` and returns the thread with my bubble and KIN's reply. On failure nothing is appended and the
    /// error is set, so the draft can stay in the field for a retry. An empty draft is not sent.
    func sending(_ draft: String, via api: KinAPI) async -> MessageThread {
        let text = String(draft.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Self.maxLength))
        guard !text.isEmpty else { return self }
        var next = self
        do {
            let out = try await api.sendMessage(text)
            next.bubbles += [Bubble(id: bubbles.count, text: text, mine: true),
                             Bubble(id: bubbles.count + 1, text: out.reply, mine: false)]
            next.error = nil
        } catch {
            next.error = "Could not send: \(error.localizedDescription)"
        }
        return next
    }
}
