import XCTest
@testable import Kin

final class LinksTests: XCTestCase {
    private func parse(_ s: String) -> Invite? { Invite.parse(URL(string: s)!) }

    func testHttpsInvite() {
        XCTAssertEqual(parse("https://kin.example.com/?call=12"), Invite(callId: 12))
        XCTAssertEqual(parse("https://kin.example.com/?call=12&key=abc"), Invite(callId: 12, key: "abc"))
        XCTAssertEqual(parse("https://kin.example.com?key=abc&call=7"), Invite(callId: 7, key: "abc"))
    }

    func testKinScheme() {
        XCTAssertEqual(parse("kin://join?call=12"), Invite(callId: 12))
        XCTAssertEqual(parse("kin://join?call=3&key=k"), Invite(callId: 3, key: "k"))
        XCTAssertEqual(parse("KIN://join?call=3"), Invite(callId: 3))
    }

    func testEmptyKeyIsNil() {
        XCTAssertEqual(parse("kin://join?call=3&key="), Invite(callId: 3))
    }

    func testInvalid() {
        for s in ["https://kin.example.com/", "https://kin.example.com/?call=abc", "https://kin.example.com/?call=0",
                  "https://kin.example.com/?call=-4", "https://kin.example.com/other?call=1", "kin://call?call=1",
                  "kin://join", "ftp://kin.example.com/?call=1", "mailto:a@b.c", "kin://join?call=1.5"] {
            XCTAssertNil(parse(s), s)
        }
    }

    func testRoundTrip() throws {
        let invite = Invite(callId: 42, key: "s3cret")
        let url = try XCTUnwrap(invite.url(host: URL(string: "https://kin.example.com/api")!))
        XCTAssertEqual(url.absoluteString, "https://kin.example.com/?call=42&key=s3cret")
        XCTAssertEqual(Invite.parse(url), invite)
        XCTAssertEqual(Invite(callId: 5).url(host: URL(string: "http://localhost:8000")!)?.absoluteString,
                       "http://localhost:8000/?call=5")
    }

    func testInviteMustBeForThisServer() {
        let base = URL(string: "http://localhost:8000")!
        XCTAssertTrue(Invite.isForServer(URL(string: "http://localhost:8000/?call=1")!, base: base))
        XCTAssertTrue(Invite.isForServer(URL(string: "kin://join?call=1")!, base: base))
        XCTAssertFalse(Invite.isForServer(URL(string: "http://localhost:9000/?call=1")!, base: base))
        XCTAssertFalse(Invite.isForServer(URL(string: "https://evil.example/?call=1")!, base: base))
        XCTAssertTrue(Invite.isForServer(URL(string: "https://KIN.example.com/?call=1")!,
                                         base: URL(string: "https://kin.example.com:443")!))
    }
}
