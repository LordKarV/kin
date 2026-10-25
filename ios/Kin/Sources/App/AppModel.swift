import Foundation
import SwiftUI

/// signup | home | call | ended. Same app for everyone (no roles).
@MainActor
final class AppModel: ObservableObject {
    enum Screen {
        case signup
        case home
        case call(CallController)
        case ended(callId: Int)
    }

    static let defaultBaseURL = "http://localhost:8000"
    private static let baseURLDefaultsKey = "kin.baseURL"  // debug setting

    @Published private(set) var screen: Screen
    @Published var error: String?
    @Published var joining = false
    /// An invite that arrived before sign-up; joined right after.
    @Published private(set) var pendingInvite: Invite?
    /// Bumped on every sign-in, so the home tabs rebuild (and reload) for the new account.
    @Published private(set) var account = 0
    /// The current call's invite code (from its join reply), for the share link.
    private var invite: (callId: Int, code: String)?

    @Published var baseURLString: String {
        didSet { UserDefaults.standard.set(baseURLString, forKey: Self.baseURLDefaultsKey) }
    }

    init() {
        baseURLString = UserDefaults.standard.string(forKey: Self.baseURLDefaultsKey) ?? Self.defaultBaseURL
        screen = Keychain.get("token") == nil ? .signup : .home
    }

    /// A typed server address as a URL: trimmed, with `http://` added when there is no scheme. Foundation reads
    /// "192.168.1.20:8000" as nothing and "laptop.local:8000" as scheme "laptop.local". nil when there is no host.
    nonisolated static func serverURL(_ typed: String) -> URL? {
        let s = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: s.contains("://") ? s : "http://\(s)"), url.host?.isEmpty == false else { return nil }
        return url
    }

    var baseURL: URL { Self.serverURL(baseURLString) ?? URL(string: Self.defaultBaseURL)! }
    /// Shown under the server field, so a typo does not silently become localhost.
    var serverAddressError: String? {
        Self.serverURL(baseURLString) == nil ? "Bad server address, using \(Self.defaultBaseURL)" : nil
    }
    var apiKey: String? { Keychain.get("apiKey") }
    var api: KinAPI { api(key: apiKey) }
    /// Sign-up and its language list: an invite opened before sign-up brings the key a locked server needs.
    var signupAPI: KinAPI { api(key: pendingInvite?.key ?? apiKey) }

    private func api(key: String?) -> KinAPI { KinAPI(baseURL: baseURL, token: Keychain.get("token"), apiKey: key) }

    func inviteURL(callId: Int) -> URL? {
        Invite(callId: callId, key: apiKey, code: invite?.callId == callId ? invite?.code : nil).url(host: baseURL)
    }

    /// Universal link or kin:// URL. No token yet: sign up first, then join.
    func open(_ url: URL) {
        #if DEBUG
        if let link = SignInLink.parse(url) {
            signIn(link)
            return
        }
        #endif
        guard let invite = Invite.parse(url) else {
            error = "That link is not a KIN invite."
            return
        }
        guard Invite.isForServer(url, base: baseURL) else {
            error = "This invite is for another KIN server."
            return
        }
        if case .call(let current) = screen {
            if current.callId != invite.callId { error = "Hang up first to join another call." }
            return
        }
        if Keychain.get("token") == nil {
            pendingInvite = invite
            screen = .signup
        } else {
            Task { await startCall(callId: invite.callId, key: invite.key, code: invite.code) }
        }
    }

    #if DEBUG
    /// Become one of the demo driver's people. The token is checked with GET /api/me first, so a bad link leaves the
    /// current account, server and key alone.
    func signIn(_ link: SignInLink) {
        if case .call = screen {
            error = "Hang up first to sign in as someone else."
            return
        }
        var base = baseURL
        if let server = link.server {
            guard let url = Self.serverURL(server) else {
                error = "That sign-in link has a bad server address."
                return
            }
            base = url
        }
        let key = link.key ?? apiKey
        Task {
            do {
                _ = try await KinAPI(baseURL: base, token: link.token, apiKey: key).me()
            } catch {
                self.error = "That sign-in token was rejected: \(error.localizedDescription)"
                return
            }
            if case .call = screen {
                error = "Hang up first to sign in as someone else."
                return
            }
            if link.server != nil { baseURLString = base.absoluteString }
            if let k = link.key, k != apiKey, !Keychain.set("apiKey", k) {
                error = "Could not save the link's key to the Keychain."
            }
            signedUp(token: link.token)
        }
    }
    #endif

    func signedUp(token: String) {
        guard Keychain.set("token", token) else {
            error = "Could not save your sign-in to the Keychain."
            return
        }
        account += 1
        if let invite = pendingInvite {
            pendingInvite = nil
            // Sign-up went through with the invite's key (signupAPI), so the server accepts it: keep it.
            if let k = invite.key, k != apiKey, !Keychain.set("apiKey", k) {
                error = "Could not save the invite's key to the Keychain."
            }
            Task { await startCall(callId: invite.callId, key: invite.key, code: invite.code) }
        } else {
            screen = .home
        }
    }

    func signOut(message: String? = nil) {
        Keychain.set("token", nil)
        screen = .signup
        if let message { error = message }
    }

    /// DELETE /api/me, then sign out. A failure keeps the account and says why.
    func deleteAccount() async {
        do {
            _ = try await api.deleteMe()
            signOut()
        } catch let e as KinAPIError where e.isBadToken {
            signOut(message: Self.signInAgain)
        } catch {
            self.error = "Could not delete your account: \(error.localizedDescription)"
        }
    }

    static let signInAgain = "Your sign-in is no longer valid. Please sign up again."

    /// A dead token (e.g. the server's database was reset) signs out, since retrying cannot help. Any other error,
    /// the key gate's 401 included, is left to the caller. true when it signed out.
    func signOutIfBadToken(_ error: Error) -> Bool {
        guard let e = error as? KinAPIError, e.isBadToken else { return false }
        signOut(message: Self.signInAgain)
        return true
    }

    /// `callId == nil` starts a new call. `key` is an invite's KIN key: used for this join and stored only once the
    /// server accepted it, so a junk kin:// link cannot overwrite a working key. `code` is the invite's code, needed to
    /// take a new seat in someone else's call. `camera: false` is an audio call.
    func startCall(callId: Int? = nil, key: String? = nil, code: String? = nil, camera: Bool = true) async {
        guard !joining else { return }
        if case .call = screen { return }  // one call at a time
        joining = true
        defer { joining = false }
        do {
            let api = api(key: key ?? apiKey)
            let join = try await api.joinWorld(callId: callId, invite: code)
            if let key, key != apiKey, !Keychain.set("apiKey", key) {
                error = "Could not save the invite's key to the Keychain."
            }
            invite = (join.invite ?? code).map { (callId: join.callId, code: $0) }
            // Both callbacks check that this call is still on screen, so a late event never replaces a newer screen.
            let id = join.callId
            let call = CallController(api: api, join: join, onEnded: { [weak self] _ in
                guard let self, case .call(let c) = self.screen, c.callId == id else { return }
                self.screen = .ended(callId: id)
            }, onFailed: { [weak self] message in
                guard let self, case .call(let c) = self.screen, c.callId == id else { return }
                self.screen = .home
                self.error = message
            })
            screen = .call(call)
            // ponytail: CallController (4E) still reads a one-shot flag; pass `camera` to connect(camera:) once it takes one.
            if !camera { CallController.audioOnlyNext = true }
            await call.connect()
        } catch let e as KinAPIError where e.isBadToken {
            signOut(message: "Please sign up again.")
        } catch {  // includes the key gate's 401: a wrong key must not cost the user their token
            self.error = error.localizedDescription
            screen = .home
        }
    }

    func backHome() { screen = .home }
}
