import Foundation

/// Invite links: `https://<host>/?call=N[&key=K]` (web form, what Share sends) and `kin://join?call=N[&key=K]`
/// (registered URL scheme). `key` is the KIN API key, needed only when the backend is locked.
struct Invite: Equatable, Sendable {
    let callId: Int
    let key: String?

    init(callId: Int, key: String? = nil) { self.callId = callId; self.key = key }

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
        let key = items.first(where: { $0.name == "key" })?.value.flatMap { $0.isEmpty ? nil : $0 }
        return Invite(callId: id, key: key)
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
        c.queryItems = [URLQueryItem(name: "call", value: String(callId))] + (key.map { [URLQueryItem(name: "key", value: $0)] } ?? [])
        return c.url
    }
}
