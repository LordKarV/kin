import XCTest
@testable import Kin

/// The Add person request flow (Connect/ConnectFlow.swift) against the stubbed URLProtocol in ExplainTests (no network).
@MainActor
final class ConnectTests: XCTestCase {
    private let api = KinAPI(baseURL: URL(string: "http://kin.test")!, token: "tok", apiKey: nil)

    override func setUp() async throws { URLProtocol.registerClass(StubProtocol.self) }

    override func tearDown() async throws {
        URLProtocol.unregisterClass(StubProtocol.self)
        StubProtocol.status = 200
        StubProtocol.reply = Data()
    }

    func testRequestFlow() async throws {
        StubProtocol.reply = Data(#"{"status":"pending","user":{"slug":"p_mei_4","name":"Mei"}}"#.utf8)
        let sent = await ConnectFlow.send("  mei-1234 ", via: api)
        XCTAssertEqual(sent, .sent(name: "Mei"))
        XCTAssertEqual(sent?.message, "Request sent to Mei.")
        let req = try XCTUnwrap(StubProtocol.last)
        XCTAssertEqual(req.httpMethod, "POST")
        XCTAssertEqual(req.url?.path, "/api/connect")
        XCTAssertEqual(req.value(forHTTPHeaderField: "X-KIN-User"), "tok")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(StubProtocol.lastBody)) as? [String: Any])
        XCTAssertEqual(body["handle"] as? String, "mei-1234")

        StubProtocol.reply = Data(#"{"status":"accepted","user":{"slug":"p_mei_4","name":"Mei"}}"#.utf8)
        let connected = await ConnectFlow.send("mei-1234", via: api)
        XCTAssertEqual(connected?.isConnected, true)

        StubProtocol.status = 404
        StubProtocol.reply = Data(#"{"detail":"no one with that handle"}"#.utf8)
        let unknown = await ConnectFlow.send("nobody-0000", via: api)
        XCTAssertEqual(unknown?.message, "No one with that handle.")

        StubProtocol.last = nil
        let blank = await ConnectFlow.send("   ", via: api)
        XCTAssertNil(blank)
        XCTAssertNil(StubProtocol.last)

        StubProtocol.status = 200
        StubProtocol.reply = Data(#"[{"from":{"slug":"p_arjun_3","name":"Arjun"},"created_at":"2026-10-25T12:00:00+00:00"}]"#.utf8)
        let incoming = try await api.connectRequests()
        XCTAssertEqual(incoming.map(\.from.name), ["Arjun"])
        StubProtocol.reply = Data(#"{"status":"accepted"}"#.utf8)
        _ = try await api.answerRequest(from: "p_arjun_3", accept: true)
        XCTAssertEqual(StubProtocol.last?.url?.path, "/api/connect/p_arjun_3/accept")
    }

    func testContactEventsDecode() {
        XCTAssertEqual(CallEvent.decode(Data(#"{"type":"contact.request","from":{"slug":"p_a_1","name":"A"}}"#.utf8)), .contacts)
        XCTAssertEqual(CallEvent.decode(Data(#"{"type":"contact.accepted","user":{"slug":"p_a_1","name":"A"}}"#.utf8)), .contacts)
    }
}
