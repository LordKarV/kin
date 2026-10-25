import Foundation

// Value types for the non-call screens, mirroring the REST shapes in ARCHITECTURE 9.2 (field names match the JSON).
// They are not in Contracts.swift yet; when the build adds them, delete these and keep the views.

public struct Contact: Codable, Sendable, Identifiable {
    public var id: String { person }
    public let person: String, name: String, lang: String, render: String, circle: String
    public let native: String?      // proposed: initial in the person's own script, for the avatar
    public let place: String?       // proposed: city, for "11:04 PM in Shanghai"
    public let localTime: String?   // proposed: derived from a `tz` field
    enum CodingKeys: String, CodingKey { case person, name, lang, render, circle, native, place; case localTime = "local_time" }
}

public struct HeardBy: Codable, Sendable { public let person: String, name: String, via: String }

public struct MeFact: Codable, Sendable, Identifiable {
    public let id: Int
    public let text: String, subject: String, speaker: String
    public let sourceKind: String, saidAt: String, status: String, sensitiveKind: String
    public let pinned: Bool
    public let expiresAt: String?
    public let heardBy: [HeardBy]
    enum CodingKeys: String, CodingKey {
        case id, text, subject, speaker, status, pinned
        case sourceKind = "source_kind", saidAt = "said_at", sensitiveKind = "sensitive_kind", expiresAt = "expires_at", heardBy = "heard_by"
    }
}

public extension Sample {
    static let contacts: [Contact] = decode(#"""
    [{"person":"p_paatti_2","name":"Kamala Paatti","lang":"ta","render":"Your grandmother","circle":"family","native":"க","place":"Madurai","local_time":"9:34 AM"},
     {"person":"p_mei_5","name":"Mei","lang":"zh","render":"Friend from high school","circle":"friends","native":"美","place":"Shanghai","local_time":"11:04 PM"},
     {"person":"p_priya_4","name":"Priya","lang":"en","render":"Friend from high school","circle":"friends","native":null,"place":"Atlanta","local_time":"12:04 PM"}]
    """#)

    /// GET /api/me/facts -> about_me (Arjun's own news) with who has heard each one.
    static let myFacts: [MeFact] = decode(#"""
    [{"id":41,"text":"Started bouldering","subject":"p_arjun_3","speaker":"p_arjun_3","source_kind":"sms","said_at":"2026-10-03","status":"active","sensitive_kind":"","pinned":false,"expires_at":null,
      "heard_by":[{"person":"p_priya_4","name":"Priya","via":"call"}]},
     {"id":44,"text":"Got an internship offer","subject":"p_arjun_3","speaker":"p_arjun_3","source_kind":"sms","said_at":"2026-10-21","status":"active","sensitive_kind":"","pinned":false,"expires_at":null,
      "heard_by":[{"person":"p_priya_4","name":"Priya","via":"call"}]},
     {"id":38,"text":"Went hiking with Mei when she visited","subject":"p_arjun_3","speaker":"p_arjun_3","source_kind":"call","said_at":"2026-09-28","status":"active","sensitive_kind":"","pinned":false,"expires_at":null,
      "heard_by":[{"person":"p_mei_5","name":"Mei","via":"call"}]}]
    """#)

    /// Third parties Arjun has heard about (not KIN users): kept only for people who heard them, and they expire.
    static let thirdParty: [MeFact] = decode(#"""
    [{"id":17,"text":"Lin: Mei's friend from the Fudan climbing wall","subject":"p_lin_17","speaker":"p_mei_5","source_kind":"call","said_at":"2026-09-14","status":"active","sensitive_kind":"","pinned":true,"expires_at":null,"heard_by":[]},
     {"id":52,"text":"Saroja: Paatti's younger sister","subject":"p_saroja_9","speaker":"p_paatti_2","source_kind":"call","said_at":"2026-10-12","status":"active","sensitive_kind":"","pinned":false,"expires_at":"2027-02-09","heard_by":[]},
     {"id":53,"text":"Saroja's health","subject":"p_saroja_9","speaker":"p_paatti_2","source_kind":"call","said_at":"2026-10-12","status":"active","sensitive_kind":"health","pinned":false,"expires_at":"2027-02-09","heard_by":[]}]
    """#)
}
