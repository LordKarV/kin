import Foundation

// REST shapes for the People, person-world and Messages screens (backend/app/world/
// contracts.py FactRow/FactsOut/DeletePersonOut). Contracts.swift does not have them yet; field names match the JSON.

struct HeardBy: Codable, Sendable, Equatable {
    let person: String
    let name: String
    let via: String
}

/// GET /api/me/facts row ("Fact" in 9.2).
struct FactRow: Codable, Sendable, Equatable, Identifiable {
    let id: Int
    let text: String
    let subject: String
    let speaker: String?
    let sourceKind: String
    let saidAt: String  // ISO datetime
    let status: String
    let sensitiveKind: String
    let pinned: Bool
    let expiresAt: String?
    let heardBy: [HeardBy]
    enum CodingKeys: String, CodingKey {
        case id, text, subject, speaker, status, pinned
        case sourceKind = "source_kind", saidAt = "said_at", sensitiveKind = "sensitive_kind"
        case expiresAt = "expires_at", heardBy = "heard_by"
    }
}

extension FactRow {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        text = try c.decode(String.self, forKey: .text)
        subject = try c.decode(String.self, forKey: .subject)
        speaker = try c.decodeIfPresent(String.self, forKey: .speaker)
        sourceKind = try c.decode(.sourceKind, or: "call")
        saidAt = try c.decode(.saidAt, or: "")
        status = try c.decode(.status, or: "active")
        sensitiveKind = try c.decode(.sensitiveKind, or: "")
        pinned = try c.decode(.pinned, or: false)
        expiresAt = try c.decodeIfPresent(String.self, forKey: .expiresAt)
        heardBy = try c.decode(.heardBy, or: [HeardBy]())
    }

    /// "2026-10-03T12:00:00" -> "Oct 3".
    var day: String { StorylineCard.day(String(saidAt.prefix(10))) }
}

struct FactsOut: Codable, Sendable, Equatable {
    let aboutMe: [FactRow]
    let iSaid: [FactRow]
    enum CodingKeys: String, CodingKey { case aboutMe = "about_me", iSaid = "i_said" }
}

struct FactPatch: Encodable { let text: String }
struct DeletedOut: Decodable { let deleted: Bool }
struct DeletePersonOut: Decodable {
    let deletedFacts: Int
    let personDeleted: Bool
    enum CodingKeys: String, CodingKey { case deletedFacts = "deleted_facts", personDeleted = "person_deleted" }
}

/// GET /api/me, read only for KIN's SMS number. Known limit: MeOut has no `sms_number` today (only the sign-up reply
/// does); decoding it optionally here shows the number as soon as the server adds it.
struct MeSms: Decodable { let smsNumber: String?; enum CodingKeys: String, CodingKey { case smsNumber = "sms_number" } }

extension KinAPI {
    func facts() async throws -> FactsOut { try await request("GET", "/api/me/facts") }
    func smsNumber() async throws -> String? { (try await request("GET", "/api/me") as MeSms).smsNumber }
    func correctFact(_ id: Int, text: String) async throws -> FactRow {
        try await request("PATCH", "/api/me/facts/\(id)", body: FactPatch(text: text))
    }
    func deleteFact(_ id: Int) async throws { _ = try await request("DELETE", "/api/me/facts/\(id)") as DeletedOut }
    func forgetPerson(_ slug: String) async throws -> DeletePersonOut {
        let safe = slug.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? slug
        return try await request("DELETE", "/api/me/world/people/\(safe)")
    }
}

/// One person's world as the screen shows it, derived from GET /api/world and GET /api/me/facts. Only what the
/// server already decided I may see; nothing is inferred here.
struct PersonWorld: Equatable {
    struct Linked: Equatable, Identifiable {
        let person: WorldPerson
        let line: String     // who they are, rendered for me
        let source: String   // where it came from
        var id: String { person.person }
    }
    var people: [Linked] = []
    var storylines: [WorldStoryline] = []
    var places: [WorldThing] = []
    var said: [FactRow] = []  // what I said about them: these I can correct or delete

    static func build(slug: String, name: String, world: WorldOut, facts: FactsOut?) -> PersonWorld {
        var out = PersonWorld()
        // Known limit: WorldOut has no per-link provenance (speaker, date), so every row cites the calls with this
        // person; the tie context is added to the line when the render does not already say it.
        var context: [String: String] = [:]
        for t in world.ties where t.src == slug || t.dst == slug { context[t.src == slug ? t.dst : t.src] = t.context ?? "" }
        for e in world.edges where e.src == slug || e.dst == slug { context[e.src == slug ? e.dst : e.src] = context[e.src == slug ? e.dst : e.src] ?? "" }
        out.people = world.people
            .filter { $0.person != slug && $0.person != world.me && context[$0.person] != nil }
            .map { p in
                let base = p.render.isEmpty ? p.name : p.render
                let extra = context[p.person] ?? ""
                let line = extra.isEmpty || base.localizedCaseInsensitiveContains(extra) ? base : "\(base), \(extra)"
                return Linked(person: p, line: line, source: "From your calls with \(name)")
            }
        out.storylines = world.storylines.filter { $0.owner == slug }  // a title rarely names its owner ("job search")
        out.places = world.things.filter { $0.owner == slug }
        out.said = (facts?.iSaid ?? []).filter { $0.subject == slug }
        return out
    }
}
