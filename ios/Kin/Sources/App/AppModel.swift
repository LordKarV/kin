import Foundation
import os
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

    /// The build's server (KIN_DEFAULT_SERVER, for example the Vultr host), else a server on this Mac.
    static let defaultBaseURL: String = {
        let configured = ((Bundle.main.object(forInfoDictionaryKey: "KINDefaultServer") as? String) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return configured.isEmpty || configured.hasPrefix("$(") ? "http://localhost:8000" : configured
    }()
    private static let baseURLDefaultsKey = "kin.baseURL"  // debug setting

    @Published private(set) var screen: Screen
    @Published var error: String?
    @Published var joining = false
    /// An invite that arrived before sign-up; joined right after.
    @Published private(set) var pendingInvite: Invite?
    /// Bumped on every sign-in, so the home tabs rebuild (and reload) for the new account.
    @Published private(set) var account = 0
    /// Bumped on a contact.request or contact.accepted event, so People reloads (Connect/).
    @Published private(set) var contactsVersion = 0
    /// The current call's invite code (from its join reply), for the share link.
    private var invite: (callId: Int, code: String)?
    /// Ringing before a call (Calling/RingState.swift); RootView covers every screen while it is not idle.
    @Published private(set) var ring: RingState = .idle {
        didSet {
            tone.update(ring)
            syncEvents()
        }
    }
    private lazy var tone = RingTone()
    private var events: EventSocket?
    private var sceneActive = false
    private static let log = Logger(subsystem: "dev.kin.app", category: "ring")

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
    /// Sign in as the person in a kin://signin link. The token is checked with GET /api/me first, so a bad link leaves
    /// the current account, server and key alone.
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
            restartEvents()  // after the key is saved: a locked server closes a keyless event socket
            Task { await startCall(callId: invite.callId, key: invite.key, code: invite.code) }
        } else {
            restartEvents()
            screen = .home
        }
    }

    func signOut(message: String? = nil) {
        Keychain.set("token", nil)
        restartEvents()
        ring = .idle
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
            // Known limit: CallController still reads a one-shot flag; pass `camera` to connect(camera:) once it takes one.
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

    // MARK: - ringing

    /// The server gives up on a ring at 45 s (RING_TIMEOUT_S); after this the app treats it as missed, in case the
    /// end never reached it (app suspended, socket dropped, server restarted).
    static let ringTimeout: Double = 50

    /// Scene phase from RootView: the event socket runs while the app is active (no push without a paid Apple
    /// account). .inactive (Control Center, an alert) keeps it, so a ring is not lost to a glance away.
    func scene(active: Bool?) {
        guard let active, active != sceneActive else { return }
        sceneActive = active
        syncEvents()
    }

    /// Active, or ringing in the background: the ring's audio (UIBackgroundModes audio) keeps the app running, so the
    /// socket can still hear "cancelled" or "answered" after the side button locks the phone.
    private var wantsEvents: Bool { sceneActive || RingTone.kind(for: ring) != nil }

    private func syncEvents() {
        if wantsEvents != (events != nil) { restartEvents() }
    }

    private func restartEvents() {
        let old = events
        events = nil
        Task { await old?.stop() }
        guard wantsEvents, Keychain.get("token") != nil else { return }
        let base = baseURL
        let socket = EventSocket(makeRequest: {
            Keychain.get("token").flatMap { EventSocket.request(base: base, token: $0, apiKey: Keychain.get("apiKey")) }
        }) { [weak self] event in await self?.handle(event) }
        events = socket
        Task { await socket.start() }
    }

    private var busy: Bool {
        if case .call = screen { return true }
        return joining
    }

    func handle(_ event: CallEvent) {
        if event == .contacts { contactsVersion += 1; return }
        if case .incoming(let id, _, _) = event, busy {
            Task { await perform(.decline(id)) }  // already in a call: the caller hears "declined" now, not in 45 s
            return
        }
        send(.event(event))
    }

    func send(_ action: RingAction) {
        let (next, effect) = ring.reduce(action)
        let started = next.startedRing(from: ring)
        ring = next
        if let effect { Task { await perform(effect) } }
        if let id = started {
            Task {  // a no-op once the ring is over: the reducer ignores a miss for any other call
                try? await Task.sleep(for: .seconds(Self.ringTimeout))
                send(.event(.missed(callId: id)))
            }
        }
    }

    /// Ring a contact (the Video / Audio buttons on a person). The call starts when they answer.
    func call(_ contact: ContactOut, video: Bool) {
        guard !busy, case .idle = ring else { return }
        send(.dial(RingPeer(slug: contact.person, name: contact.name), video: video))
        let api = self.api
        Task {
            do {
                let out = try await api.ring(to: contact.person, video: video)
                send(.dialed(callId: out.callId, delivered: out.delivered))
            } catch {
                if !signOutIfBadToken(error) {
                    send(.dialFailed("Could not call \(contact.name): \(error.localizedDescription)"))
                }
            }
        }
    }

    /// The old flow as a fallback: start a call of my own and share its invite link from the call screen.
    func shareInviteInstead() {
        let video: Bool
        switch ring {
        case .outgoing(_, _, let v, _), .unanswered(_, let v, _): video = v
        default: return
        }
        send(.cancel)
        Task { await startCall(camera: video) }
    }

    private func perform(_ effect: RingEffect) async {
        let api = self.api
        switch effect {
        case .join(let id, let video):
            await startCall(callId: id, camera: video)
        case .answer(let id, let video):
            do {
                _ = try await api.answer(callId: id)
            } catch {
                if !signOutIfBadToken(error) { self.error = "Could not answer: \(error.localizedDescription)" }
                return
            }
            await startCall(callId: id, camera: video)
        case .decline(let id):
            do { _ = try await api.decline(callId: id) } catch {
                Self.log.info("decline \(id) failed: \(error.localizedDescription)")  // the ring is over anyway
            }
        case .cancel(let id):
            do { _ = try await api.cancelRing(callId: id) } catch {
                Self.log.info("cancel \(id) failed: \(error.localizedDescription)")  // it times out as missed
            }
        }
    }
}
