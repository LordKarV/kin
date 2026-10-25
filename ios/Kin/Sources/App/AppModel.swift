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

    @Published var baseURLString: String {
        didSet { UserDefaults.standard.set(baseURLString, forKey: Self.baseURLDefaultsKey) }
    }

    init() {
        baseURLString = UserDefaults.standard.string(forKey: Self.baseURLDefaultsKey) ?? Self.defaultBaseURL
        screen = Keychain.get("token") == nil ? .signup : .home
    }

    var baseURL: URL { URL(string: baseURLString) ?? URL(string: Self.defaultBaseURL)! }
    var apiKey: String? { Keychain.get("apiKey") }
    var api: KinAPI { api(key: apiKey) }

    private func api(key: String?) -> KinAPI { KinAPI(baseURL: baseURL, token: Keychain.get("token"), apiKey: key) }

    func inviteURL(callId: Int) -> URL? { Invite(callId: callId, key: apiKey).url(host: baseURL) }

    /// Universal link or kin:// URL. No token yet: sign up first, then join.
    func open(_ url: URL) {
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
            Task { await startCall(callId: invite.callId, key: invite.key) }
        }
    }

    func signedUp(token: String) {
        guard Keychain.set("token", token) else {
            error = "Could not save your sign-in to the Keychain."
            return
        }
        if let invite = pendingInvite {
            pendingInvite = nil
            Task { await startCall(callId: invite.callId, key: invite.key) }
        } else {
            screen = .home
        }
    }

    func signOut() {
        Keychain.set("token", nil)
        screen = .signup
    }

    /// `callId == nil` starts a new call. `key` is an invite's KIN key: used for this join and stored only once the
    /// server accepted it, so a junk kin:// link cannot overwrite a working key.
    func startCall(callId: Int? = nil, key: String? = nil) async {
        guard !joining else { return }
        if case .call = screen { return }  // one call at a time
        joining = true
        defer { joining = false }
        do {
            let api = api(key: key ?? apiKey)
            let join = try await api.joinWorld(callId: callId)
            if let key, key != apiKey, !Keychain.set("apiKey", key) {
                error = "Could not save the invite's key to the Keychain."
            }
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
            await call.connect()
        } catch let e as KinAPIError where e.status == 401 {
            signOut()
            error = "Please sign up again."
        } catch {
            self.error = error.localizedDescription
            screen = .home
        }
    }

    func backHome() { screen = .home }
}
