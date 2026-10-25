import Foundation

/// PATCH /api/me body (backend MePatch): only the language, so name and phone stay as they are.
struct MeLangPatch: Encodable { let lang: String }

extension KinAPI {
    /// Change the language I speak. A call in progress keeps its language; the next call uses this one.
    func setLanguage(_ code: String) async throws -> MeOut { try await send("PATCH", "/api/me", MeLangPatch(lang: code)) }
}
