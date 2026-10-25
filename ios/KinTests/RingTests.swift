import XCTest
@testable import Kin

/// Ringing (Calling/): event decoding, the ring state machine, and the event socket request. No network.
final class RingTests: XCTestCase {
    let mei = RingPeer(slug: "p_mei_5", name: "Mei")
    let arjun = RingPeer(slug: "p_arjun_3", name: "Arjun")

    private func event(_ json: String) -> CallEvent? { CallEvent.decode(Data(json.utf8)) }

    func testDecodesServerEvents() {
        XCTAssertEqual(event(#"{"type":"call.incoming","call_id":7,"from":{"slug":"p_arjun_3","name":"Arjun"},"video":false}"#),
                       .incoming(callId: 7, from: arjun, video: false))
        XCTAssertEqual(event(#"{"type":"call.answered","call_id":7}"#), .answered(callId: 7))
        XCTAssertEqual(event(#"{"type":"call.declined","call_id":7}"#), .declined(callId: 7))
        XCTAssertEqual(event(#"{"type":"call.cancelled","call_id":7}"#), .cancelled(callId: 7))
        XCTAssertEqual(event(#"{"type":"call.missed","call_id":7}"#), .missed(callId: 7))
        XCTAssertEqual(event(#"{"type":"ping"}"#), .ping)
        XCTAssertNil(event(#"{"type":"call.later","call_id":7}"#))
        XCTAssertNil(event(#"{"type":"call.incoming","call_id":7}"#), "an incoming ring without a caller is dropped")
        XCTAssertNil(event("not json"))
        let out = try? JSONDecoder().decode(RingOut.self, from: Data(#"{"call_id":9,"delivered":false}"#.utf8))
        XCTAssertEqual(out, RingOut(callId: 9, delivered: false))
    }

    func testOutgoingAnsweredJoinsWithTheRingsVideoChoice() {
        var (s, fx) = RingState.idle.reduce(.dial(mei, video: false))
        XCTAssertEqual(s, .outgoing(callId: nil, peer: mei, video: false, delivered: true))
        XCTAssertNil(fx)
        (s, fx) = s.reduce(.dialed(callId: 7, delivered: false))
        XCTAssertEqual(s, .outgoing(callId: 7, peer: mei, video: false, delivered: false))
        XCTAssertEqual(s.reduce(.event(.answered(callId: 8))).0, s, "another call's answer is ignored")
        (s, fx) = s.reduce(.event(.answered(callId: 7)))
        XCTAssertEqual(s, .idle)
        XCTAssertEqual(fx, .join(callId: 7, video: false))
    }

    func testDeclinedMissedAndFailedOfferTheInvite() {
        let ringing = RingState.outgoing(callId: 7, peer: mei, video: true, delivered: true)
        XCTAssertEqual(ringing.reduce(.event(.declined(callId: 7))).0,
                       .unanswered(peer: mei, video: true, message: "Mei declined the call."))
        XCTAssertEqual(ringing.reduce(.event(.missed(callId: 7))).0,
                       .unanswered(peer: mei, video: true, message: "Mei didn't answer."))
        let dialing = RingState.outgoing(callId: nil, peer: mei, video: true, delivered: true)
        let failed = dialing.reduce(.dialFailed("Could not call Mei")).0
        XCTAssertEqual(failed, .unanswered(peer: mei, video: true, message: "Could not call Mei"))
        XCTAssertEqual(failed.reduce(.dismiss).0, .idle)
    }

    func testCancelBeforeAndAfterTheServerAnswers() {
        let ringing = RingState.outgoing(callId: 7, peer: mei, video: true, delivered: true)
        XCTAssertEqual(ringing.reduce(.cancel).0, .idle)
        XCTAssertEqual(ringing.reduce(.cancel).1, .cancel(7))
        let dialing = RingState.outgoing(callId: nil, peer: mei, video: true, delivered: true)
        let (s, fx) = dialing.reduce(.cancel)
        XCTAssertEqual(s, .idle)
        XCTAssertNil(fx)
        XCTAssertEqual(s.reduce(.dialed(callId: 7, delivered: true)).1, .cancel(7), "a late ring reply is cancelled")
    }

    func testIncomingAcceptDeclineCancelledAndBusy() {
        let (s, _) = RingState.idle.reduce(.event(.incoming(callId: 7, from: arjun, video: true)))
        XCTAssertEqual(s, .incoming(callId: 7, peer: arjun, video: true))
        XCTAssertEqual(s.reduce(.answer).1, .answer(callId: 7, video: true))
        XCTAssertEqual(s.reduce(.decline).1, .decline(7))
        XCTAssertEqual(s.reduce(.event(.cancelled(callId: 7))).0, .idle)
        XCTAssertEqual(s.reduce(.event(.missed(callId: 7))).0, .idle)
        XCTAssertEqual(s.reduce(.event(.incoming(callId: 7, from: arjun, video: true))).1, nil, "a replay is not a new ring")
        let busy = s.reduce(.event(.incoming(callId: 8, from: mei, video: true)))
        XCTAssertEqual(busy.0, s)
        XCTAssertEqual(busy.1, .decline(8))
        let ringingOut = RingState.outgoing(callId: 5, peer: mei, video: true, delivered: true)
        XCTAssertEqual(ringingOut.reduce(.event(.incoming(callId: 9, from: arjun, video: true))).1, .decline(9))
    }

    func testTimeoutStartsOnceARingHasAnId() {
        let dialing = RingState.outgoing(callId: nil, peer: mei, video: true, delivered: true)
        let ringing = RingState.outgoing(callId: 7, peer: mei, video: true, delivered: true)
        XCTAssertNil(dialing.startedRing(from: .idle), "no call id yet")
        XCTAssertEqual(ringing.startedRing(from: dialing), 7)
        XCTAssertNil(ringing.startedRing(from: ringing))
        let called = RingState.incoming(callId: 9, peer: arjun, video: true)
        XCTAssertEqual(called.startedRing(from: .idle), 9)
        XCTAssertNil(called.startedRing(from: called), "a replayed ring keeps its first timer")
        XCTAssertNil(RingState.idle.startedRing(from: called))
    }

    func testToneFollowsTheRing() {
        XCTAssertEqual(RingTone.kind(for: .outgoing(callId: nil, peer: mei, video: true, delivered: true)), .ringback)
        XCTAssertEqual(RingTone.kind(for: .incoming(callId: 7, peer: arjun, video: true)), .ringtone)
        XCTAssertNil(RingTone.kind(for: .idle))
        XCTAssertNil(RingTone.kind(for: .unanswered(peer: mei, video: true, message: "")))
    }

    func testEventSocketRequest() throws {
        let r = try XCTUnwrap(EventSocket.request(base: URL(string: "https://kin.example.com")!, token: "tok", apiKey: "k"))
        XCTAssertEqual(r.url?.absoluteString, "wss://kin.example.com/ws/events")
        XCTAssertEqual(r.value(forHTTPHeaderField: "X-KIN-User"), "tok")
        XCTAssertEqual(r.value(forHTTPHeaderField: "X-KIN-Key"), "k")
        let local = try XCTUnwrap(EventSocket.request(base: URL(string: "http://192.168.1.20:8000")!, token: "tok", apiKey: nil))
        XCTAssertEqual(local.url?.absoluteString, "ws://192.168.1.20:8000/ws/events")
        XCTAssertNil(local.value(forHTTPHeaderField: "X-KIN-Key"))
        XCTAssertEqual(EventSocket.backoff(attempt: 0), 1)
        XCTAssertEqual(EventSocket.backoff(attempt: 20), EventSocket.maxBackoff)
    }
}
