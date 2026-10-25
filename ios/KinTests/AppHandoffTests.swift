import XCTest
@testable import Kin

final class AppHandoffTests: XCTestCase {
    private let key = MessagesScreen.savedNumberKey

    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: key)
        super.tearDown()
    }

    private func signup(sms: String?) -> UserOut {
        UserOut(userId: 1, personId: 2, person: "Arjun", spaceId: 3, token: "t", smsNumber: sms)
    }

    @MainActor func testSignupSavesTheSmsNumberMessagesScreenReads() {
        SignupView.saveSmsNumber(signup(sms: "+15125550100"))
        XCTAssertEqual(UserDefaults.standard.string(forKey: key), "+15125550100")
    }

    // A stale number from an earlier sign-up must not outlive a sign-up that has none.
    @MainActor func testNilSmsNumberClearsTheSavedNumber() {
        UserDefaults.standard.set("+15125550199", forKey: key)
        SignupView.saveSmsNumber(signup(sms: nil))
        XCTAssertNil(UserDefaults.standard.object(forKey: key))
    }

    // config.py sends "" when no number is configured; saving it would be noise over GET /api/me.
    @MainActor func testEmptySmsNumberIsNotSaved() {
        UserDefaults.standard.set("+15125550199", forKey: key)
        SignupView.saveSmsNumber(signup(sms: ""))
        XCTAssertNil(UserDefaults.standard.object(forKey: key))
    }

    // MARK: - server address, sign-in, 401s (AppModel against a stubbed server)

    func testTypedServerAddressGetsAScheme() {
        XCTAssertEqual(AppModel.serverURL("192.168.1.20:8000")?.absoluteString, "http://192.168.1.20:8000")
        XCTAssertEqual(AppModel.serverURL("  http://192.168.1.20:8000 \n")?.absoluteString, "http://192.168.1.20:8000")
        XCTAssertEqual(AppModel.serverURL("laptop.local:8000")?.host, "laptop.local")
        XCTAssertEqual(AppModel.serverURL("https://kin.example.com")?.absoluteString, "https://kin.example.com")
        XCTAssertNil(AppModel.serverURL(""))
        XCTAssertNil(AppModel.serverURL("http://"))
    }

    func testOnlyTokenRejectionsCountAsBadToken() {
        XCTAssertTrue(KinAPIError(status: 401, message: "X-KIN-User token required").isBadToken)
        XCTAssertTrue(KinAPIError(status: 401, message: "X-KIN-User token required (returned once by POST /api/users)").isBadToken)
        XCTAssertFalse(KinAPIError(status: 401, message: "KIN API key required (X-KIN-Key header, Authorization: Bearer, or ?key=)").isBadToken)
        XCTAssertFalse(KinAPIError(status: 404, message: "X-KIN-User").isBadToken)
    }
}

/// Answers every request to http://stub.kin.test with `handler`, through URLSession.shared (what KinAPI uses).
final class StubServer: URLProtocol {
    nonisolated(unsafe) static var handler: (@Sendable (URLRequest, Data) -> (Int, String))?
    nonisolated(unsafe) static var seen: [(URLRequest, Data)] = []

    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "stub.kin.test" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        var body = request.httpBody ?? Data()
        if body.isEmpty, let stream = request.httpBodyStream {
            stream.open()
            var buf = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable { let n = stream.read(&buf, maxLength: buf.count); if n <= 0 { break }; body.append(buf, count: n) }
            stream.close()
        }
        Self.seen.append((request, body))
        let (status, text) = Self.handler?(request, body) ?? (500, #"{"detail":"no handler"}"#)
        let resp = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                   headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(text.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@MainActor
final class AppModelTests: XCTestCase {
    private var saved: (token: String?, key: String?, base: Any?)
    nonisolated private static let me = #"{"user_id":1,"person_id":2,"person":"p_arjun_2","name":"Arjun","lang":"en","phone":null}"#

    override func setUp() async throws {
        saved = (Keychain.get("token"), Keychain.get("apiKey"), UserDefaults.standard.object(forKey: "kin.baseURL"))
        Keychain.set("token", nil)
        Keychain.set("apiKey", nil)
        UserDefaults.standard.set("http://stub.kin.test:8000", forKey: "kin.baseURL")
        URLProtocol.registerClass(StubServer.self)
        StubServer.seen = []
    }

    override func tearDown() async throws {
        URLProtocol.unregisterClass(StubServer.self)
        StubServer.handler = nil
        Keychain.set("token", saved.token)
        Keychain.set("apiKey", saved.key)
        UserDefaults.standard.set(saved.base, forKey: "kin.baseURL")
    }

    private func eventually(_ what: String, _ check: () -> Bool) async throws {
        for _ in 0..<200 where !check() { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertTrue(check(), what)
    }

    private func isHome(_ model: AppModel) -> Bool { if case .home = model.screen { return true }; return false }

    func testSignInLinkChecksTheTokenBeforeSwitchingAccount() async throws {
        StubServer.handler = { req, _ in
            req.value(forHTTPHeaderField: "X-KIN-User") == "good" ? (200, Self.me) : (401, #"{"detail":"X-KIN-User token required"}"#)
        }
        Keychain.set("token", "mine")
        let model = AppModel()
        model.open(URL(string: "kin://signin?token=bad&server=http%3A%2F%2Fstub.kin.test%3A9000")!)
        try await eventually("a rejected token says so") { model.error != nil }
        XCTAssertEqual(Keychain.get("token"), "mine")
        XCTAssertEqual(model.baseURLString, "http://stub.kin.test:8000")  // a bad link leaves the server alone

        model.error = nil
        model.open(URL(string: "kin://signin?token=good&server=stub.kin.test%3A8000&key=k1")!)
        try await eventually("signed in as the link's person") { Keychain.get("token") == "good" }
        XCTAssertEqual(model.baseURL.absoluteString, "http://stub.kin.test:8000")
        XCTAssertEqual(Keychain.get("apiKey"), "k1")
        XCTAssertEqual(model.account, 1)  // the home tabs rebuild for the new account
        XCTAssertTrue(isHome(model))
        XCTAssertNil(model.error)
    }

    func testKeyGate401KeepsTheTokenButADeadTokenSignsOut() async throws {
        Keychain.set("token", "t1")
        let model = AppModel()
        StubServer.handler = { _, _ in (401, #"{"detail":"KIN API key required (X-KIN-Key header, Authorization: Bearer, or ?key=)"}"#) }
        await model.startCall(callId: 3, key: "wrong", code: "c0de")
        XCTAssertEqual(Keychain.get("token"), "t1")
        XCTAssertNil(Keychain.get("apiKey"))  // a rejected invite key is not stored either
        XCTAssertEqual(model.error, "KIN API key required (X-KIN-Key header, Authorization: Bearer, or ?key=)")
        let body = try XCTUnwrap(StubServer.seen.last?.1)
        let sent = try JSONSerialization.jsonObject(with: body) as? [String: Any]
        XCTAssertEqual(sent?["call_id"] as? Int, 3)
        XCTAssertEqual(sent?["invite"] as? String, "c0de")  // the invite code reaches /api/rtc/join

        StubServer.handler = { _, _ in (401, #"{"detail":"X-KIN-User token required"}"#) }
        await model.startCall()
        XCTAssertNil(Keychain.get("token"))
        if case .signup = model.screen {} else { XCTFail("a dead token should go back to sign-up") }
    }

    func testDeleteAccountSignsOutOnlyOnceTheServerDeleted() async throws {
        Keychain.set("token", "t1")
        let model = AppModel()
        StubServer.handler = { _, _ in (500, #"{"detail":"x"}"#) }
        await model.deleteAccount()
        XCTAssertEqual(StubServer.seen.last?.0.httpMethod, "DELETE")
        XCTAssertEqual(StubServer.seen.last?.0.url?.path, "/api/me")
        XCTAssertEqual(Keychain.get("token"), "t1")  // a failed delete keeps the account and says why
        XCTAssertTrue(model.error?.hasPrefix("Could not delete your account") == true, model.error ?? "nil")
        XCTAssertTrue(isHome(model))

        model.error = nil
        StubServer.handler = { _, _ in (200, #"{"deleted":true,"facts":0,"utterances":0}"#) }
        await model.deleteAccount()
        XCTAssertNil(Keychain.get("token"))
        if case .signup = model.screen {} else { XCTFail("a deleted account goes back to sign-up") }
        XCTAssertNil(model.error)
    }

    func testOnlyADeadTokenSignsOutOfTheHomeTabs() {  // PeopleScreen.load
        Keychain.set("token", "t1")
        let model = AppModel()
        XCTAssertFalse(model.signOutIfBadToken(KinAPIError(status: 401, message: "KIN API key required (X-KIN-Key header, Authorization: Bearer, or ?key=)")))
        XCTAssertFalse(model.signOutIfBadToken(URLError(.notConnectedToInternet)))
        XCTAssertEqual(Keychain.get("token"), "t1")
        XCTAssertTrue(isHome(model))

        XCTAssertTrue(model.signOutIfBadToken(KinAPIError(status: 401, message: "X-KIN-User token required")))
        XCTAssertNil(Keychain.get("token"))
        if case .signup = model.screen {} else { XCTFail("a dead token goes back to sign-up") }
        XCTAssertEqual(model.error, AppModel.signInAgain)
    }

    func testSignUpUsesTheInvitesKey() {
        let model = AppModel()
        XCTAssertNil(model.signupAPI.apiKey)
        model.open(URL(string: "kin://join?call=3&key=K&code=c")!)
        XCTAssertEqual(model.pendingInvite, Invite(callId: 3, key: "K", code: "c"))
        XCTAssertEqual(model.signupAPI.apiKey, "K")  // a locked server needs it for languages and sign-up
    }
}

@MainActor
final class PersonWorldTests: XCTestCase {
    func testStorylinesAreTheOwnersNotTitleMatches() throws {
        let world = try JSONDecoder().decode(WorldOut.self, from: Data(#"""
        {"me":"p_arjun_2","people":[],"storylines":[
          {"id":1,"title":"job search","status":"active","states":[],"owner":"p_mei_5"},
          {"id":2,"title":"Mei's visit","status":"active","states":[],"owner":"p_arjun_2"},
          {"id":3,"title":"old one","status":"active","states":[]}]}
        """#.utf8))
        let out = PersonWorld.build(slug: "p_mei_5", name: "Mei", world: world, facts: nil)
        XCTAssertEqual(out.storylines.map(\.id), [1])
    }

    func testMessagesListsCallFactsAboutMeToo() throws {
        let facts = try JSONDecoder().decode(FactsOut.self, from: Data(#"""
        {"about_me":[{"id":1,"text":"started bouldering","subject":"p_arjun_2","source_kind":"message","said_at":"2026-10-03T12:00:00"},
                     {"id":2,"text":"went hiking with Mei","subject":"p_arjun_2","source_kind":"call","said_at":"2026-09-13T12:00:00",
                      "heard_by":[{"person":"p_mei_5","name":"Mei","via":"call"}]}],
         "i_said":[]}
        """#.utf8))
        XCTAssertEqual(MessagesScreen.fromTexts(facts).map(\.id), [1])
        let calls = MessagesScreen.fromCalls(facts)
        XCTAssertEqual(calls.map(\.id), [2])
        XCTAssertEqual(MessagesView.heard(calls[0]), "Said Sep 13 \u{00B7} Mei heard it")
    }
}
