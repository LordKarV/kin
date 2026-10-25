import XCTest
@testable import Kin

/// The in-app Messages send flow (KinAPI+Messages.swift) against the stubbed URLProtocol in ExplainTests (no network).
@MainActor
final class MessagesTests: XCTestCase {
    private let api = KinAPI(baseURL: URL(string: "http://kin.test")!, token: "tok", apiKey: nil)

    override func setUp() async throws { URLProtocol.registerClass(StubProtocol.self) }

    override func tearDown() async throws {
        URLProtocol.unregisterClass(StubProtocol.self)
        StubProtocol.status = 200
        StubProtocol.reply = Data()
    }

    func testSendAppendsMyTextAndKinsReply() async throws {
        StubProtocol.reply = Data(#"{"reply":"Nice: you started bouldering.","facts":[{"id":7,"text":"started bouldering","subject":"p_arjun_3","source_kind":"message","said_at":"2026-10-25T12:00:00","status":"active"}]}"#.utf8)
        let thread = await MessageThread().sending("  started bouldering  ", via: api)
        XCTAssertEqual(thread.bubbles.map(\.text), ["started bouldering", "Nice: you started bouldering."])
        XCTAssertEqual(thread.bubbles.map(\.mine), [true, false])
        XCTAssertNil(thread.error)

        let req = try XCTUnwrap(StubProtocol.last)
        XCTAssertEqual(req.httpMethod, "POST")
        XCTAssertEqual(req.url?.path, "/api/me/messages")
        XCTAssertEqual(req.value(forHTTPHeaderField: "X-KIN-User"), "tok")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(StubProtocol.lastBody)) as? [String: Any])
        XCTAssertEqual(body["text"] as? String, "started bouldering")

        let again = await thread.sending("got the internship", via: api)
        XCTAssertEqual(again.bubbles.map(\.id), [0, 1, 2, 3], "ids stay unique for ForEach")
    }

    func testFailedSendAppendsNothingAndSaysWhy() async {
        StubProtocol.status = 401
        StubProtocol.reply = Data(#"{"detail":"X-KIN-User token required"}"#.utf8)
        let thread = await MessageThread().sending("started bouldering", via: api)
        XCTAssertTrue(thread.bubbles.isEmpty)
        XCTAssertEqual(thread.error, "Could not send: X-KIN-User token required")
    }

    func testBlankDraftIsNotSent() async {
        StubProtocol.last = nil
        let thread = await MessageThread().sending("   \n", via: api)
        XCTAssertEqual(thread, MessageThread())
        XCTAssertNil(StubProtocol.last)
    }
}
