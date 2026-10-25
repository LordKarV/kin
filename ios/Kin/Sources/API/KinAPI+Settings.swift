import Foundation

/// PATCH /api/me bodies (backend MePatch): one field each, so the others stay as they are.
struct MeLangPatch: Encodable { let lang: String }
struct MeNamePatch: Encodable { let name: String }

extension KinAPI {
    /// Change the language I speak. A call in progress keeps its language; the next call uses this one.
    func setLanguage(_ code: String) async throws -> MeOut { try await send("PATCH", "/api/me", MeLangPatch(lang: code)) }

    /// Change my name. It is my person's display name, so everyone I talk to sees it (a live call keeps the old one).
    func setName(_ name: String) async throws -> MeOut { try await send("PATCH", "/api/me", MeNamePatch(name: name)) }

    /// Demo builds: put the seeded world back (POST /api/dev/reset) as part 1 (friends) or 2 (grandmother).
    func resetDemo(part: Int) async throws -> DemoResetOut { try await send("POST", "/api/dev/reset", DemoResetIn(part: part)) }
}

struct DemoResetIn: Encodable { let part: Int }
struct DemoResetOut: Decodable { let part: Int; let name: String; let lang: String }

extension KinAPI {
}
