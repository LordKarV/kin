import Foundation

/// Invite links: `https://<host>/?call=N[&key=K][&code=C]` (web form, what Share sends; the server's `/` page hands it
/// to the app as kin://join) and `kin://join?call=N[&key=K][&code=C]` (registered URL scheme). `key` is the KIN API key,
/// needed only when the backend is locked. `code` is the call's invite code: the server lets a new person join only
/// with it.
struct Invite: Equatable, Sendable {
    let callId: Int
    let key: String?
    let code: String?

    init(callId: Int, key: String? = nil, code: String? = nil) { self.callId = callId; self.key = key; self.code = code }

    /// nil for anything that is not a well-formed invite.
    static func parse(_ url: URL) -> Invite? {
        guard let c = URLComponents(url: url, resolvingAgainstBaseURL: false), let scheme = c.scheme?.lowercased()
        else { return nil }
        switch scheme {
        case "https", "http":  // ponytail: http allowed so a localhost dev invite still opens
            guard c.host?.isEmpty == false, c.path.isEmpty || c.path == "/" else { return nil }
        case "kin":
            guard c.host == "join" else { return nil }
        default:
            return nil
        }
        let items = c.queryItems ?? []
        guard let raw = items.first(where: { $0.name == "call" })?.value, let id = Int(raw), id > 0 else { return nil }
        func value(_ name: String) -> String? { items.first(where: { $0.name == name })?.value.flatMap { $0.isEmpty ? nil : $0 } }
        return Invite(callId: id, key: value("key"), code: value("code"))
    }

    /// A web invite names its server: it must be the one the app talks to, or the app would join call N on the
    /// wrong server and send it the other server's key. A kin:// invite has no host and always matches.
    static func isForServer(_ url: URL, base: URL) -> Bool {
        guard let scheme = url.scheme?.lowercased(), scheme == "https" || scheme == "http" else { return true }
        func port(_ u: URL) -> Int? { u.port ?? (u.scheme?.lowercased() == "https" ? 443 : u.scheme?.lowercased() == "http" ? 80 : nil) }
        return url.host?.lowercased() == base.host?.lowercased() && port(url) == port(base)
    }

    /// The shareable https form, on the given server's host.
    func url(host base: URL) -> URL? {
        var c = URLComponents()
        c.scheme = base.scheme ?? "https"
        c.host = base.host
        c.port = base.port
        c.path = "/"
        c.queryItems = [URLQueryItem(name: "call", value: String(callId))]
            + [("key", key), ("code", code)].compactMap { name, v in v.map { URLQueryItem(name: name, value: $0) } }
        return c.url
    }
}

#if DEBUG
/// `kin://signin?token=T[&server=URL][&key=K]`, from POST /api/dev/signin, so a phone can sign in as that person.
/// Debug builds only: in a release build a link that swaps the signed-in account is account
/// fixation.
struct SignInLink: Equatable, Sendable {
    let token: String
    let server: String?
    let key: String?

    /// nil unless this is a kin://signin link with a token.
    static func parse(_ url: URL) -> SignInLink? {
        guard url.scheme?.lowercased() == "kin", url.host?.lowercased() == "signin",
              let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else { return nil }
        func value(_ name: String) -> String? { items.first(where: { $0.name == name })?.value.flatMap { $0.isEmpty ? nil : $0 } }
        guard let token = value("token") else { return nil }
        return SignInLink(token: token, server: value("server"), key: value("key"))
    }
}
#endif
