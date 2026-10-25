import XCTest
@testable import Kin

/// The double-twist detector on synthetic 60 Hz sequences, plus the gesture's request and card handling
/// (ARCHITECTURE Amendment 7). No sensors, no network.
final class TwistDetectorTests: XCTestCase {
    private let dt = 1.0 / 60

    /// Samples from `start` for `duration` seconds; `rate` and `accel` are functions of time since `start`.
    private func seq(from start: TimeInterval = 0, _ duration: TimeInterval, rate: (Double) -> Double,
                     accel: (Double) -> Double = { _ in 0.2 }) -> [TwistSample] {
        stride(from: 0.0, to: duration, by: dt).map { x in TwistSample(t: start + x, rate: rate(x), accel: accel(x)) }
    }

    private func still(from start: TimeInterval, _ duration: TimeInterval) -> [TwistSample] {
        seq(from: start, duration, rate: { _ in 0.05 })
    }

    /// Out and back in 400 ms: one positive and one negative spike peaking at 7 rad/s. This also pins that a single
    /// out-and-back flick fires (see the ponytail note in TwistDetector).
    private func doubleTwist(at start: TimeInterval) -> [TwistSample] {
        seq(from: start, 0.4, rate: { 7 * sin(2 * .pi * $0 / 0.4) }, accel: { _ in 0.35 })
    }

    private func fireTimes(_ samples: [TwistSample]) -> [TimeInterval] {
        var d = TwistDetector()
        return samples.filter { d.feed($0) }.map(\.t)
    }

    func testDoubleTwistFiresOnce() {
        let fires = fireTimes(still(from: 0, 1) + doubleTwist(at: 1) + still(from: 1.4, 2))
        XCTAssertEqual(fires.count, 1)
        XCTAssertEqual(fires.first ?? 0, 1.49, accuracy: 0.05, "fires joltHold after the second, opposite spike")
    }

    func testSingleTwistDoesNotFire() {
        let out = seq(from: 1, 0.2, rate: { 7 * sin(.pi * $0 / 0.2) })  // one way only
        XCTAssertEqual(fireTimes(still(from: 0, 1) + out + still(from: 1.2, 2)), [])
    }

    func testSameSignSpikesDoNotFire() {
        let a = seq(from: 0, 0.1, rate: { 7 * sin(.pi * $0 / 0.1) })
        let b = seq(from: 0.3, 0.1, rate: { 7 * sin(.pi * $0 / 0.1) })  // same direction, 300 ms later
        XCTAssertEqual(fireTimes(a + still(from: 0.1, 0.2) + b + still(from: 0.4, 1)), [])
    }

    func testSpikesTooFarApartDoNotFire() {
        let out = seq(from: 1, 0.2, rate: { 7 * sin(.pi * $0 / 0.2) })
        let back = seq(from: 2, 0.2, rate: { -7 * sin(.pi * $0 / 0.2) })  // 1 s later, outside the 600 ms window
        XCTAssertEqual(fireTimes(out + still(from: 1.2, 0.8) + back), [])
    }

    func testWalkingNoiseDoesNotFire() {
        // Arm swing and heel strikes at 2 Hz: the rotation would pair up every 250 ms, but each peak comes with a
        // jolt of linear acceleration.
        let walk = seq(from: 0, 4, rate: { 4.5 * sin(2 * .pi * 2 * $0) }, accel: { 1.1 * abs(sin(2 * .pi * 2 * $0)) })
        XCTAssertEqual(fireTimes(walk), [])
    }

    func testSettingThePhoneDownDoesNotFire() {
        // A quiet flip in the hand, then the thump of landing after the second spike.
        let down = seq(from: 0, 0.5, rate: { $0 < 0.3 ? 6 * sin(2 * .pi * $0 / 0.3) : 0 },
                       accel: { $0 < 0.25 ? 0.4 : 1.5 })
        XCTAssertEqual(fireTimes(down), [])
    }

    func testSpikeRightAfterAJoltIsIgnored() {
        let bump = seq(from: 0, 0.1, rate: { _ in 0 }, accel: { $0 > 0.05 ? 1.5 : 0.2 })
        let twist = seq(from: 0.1, 0.4, rate: { 7 * sin(2 * .pi * $0 / 0.4) }, accel: { _ in 0.3 })
        XCTAssertEqual(fireTimes(bump + twist + still(from: 0.5, 1)), [], "first spike is inside joltHold")
    }

    func testJoltBetweenSpikesClearsThePair() {
        let out = seq(from: 0, 0.1, rate: { 7 * sin(.pi * $0 / 0.1) })
        let back = seq(from: 0.5, 0.1, rate: { -7 * sin(.pi * $0 / 0.1) }) + still(from: 0.6, 1)
        let quiet = seq(from: 0.1, 0.1, rate: { _ in 0 })
        let jolt = seq(from: 0.1, 0.1, rate: { _ in 0 }, accel: { _ in 1.5 })
        let gap = seq(from: 0.2, 0.3, rate: { _ in 0 })
        XCTAssertEqual(fireTimes(out + quiet + gap + back).count, 1, "control: the same pair fires without the jolt")
        XCTAssertEqual(fireTimes(out + jolt + gap + back), [])
    }

    func testSlowTiltDoesNotFire() {
        let tilt = seq(from: 0, 1.5, rate: { _ in 1.2 }) + seq(from: 1.5, 1.5, rate: { _ in -1.2 })
        XCTAssertEqual(fireTimes(tilt), [])
    }

    func testTwoTwistsThreeSecondsApartFireTwice() {
        let fires = fireTimes(doubleTwist(at: 0) + still(from: 0.4, 2.6) + doubleTwist(at: 3) + still(from: 3.4, 1))
        XCTAssertEqual(fires.count, 2)
    }

    func testSecondTwistInsideTheDebounceIsIgnored() {
        let fires = fireTimes(doubleTwist(at: 0) + still(from: 0.4, 0.6) + doubleTwist(at: 1) + still(from: 1.4, 1))
        XCTAssertEqual(fires.count, 1, "debounced for 2 s")
    }
}

/// The gesture's request and what it does to the call screen's state.
@MainActor
final class RecentExplainTests: XCTestCase {
    let t0 = Date(timeIntervalSince1970: 2_000_000)

    private var lin: GlanceItem {
        try! JSONDecoder().decode(GlanceItem.self, from: Data(#"{"key":"who:p_lin_17","kind":"who","title":"Lin","native":"林","node_id":"p_lin_17"}"#.utf8))
    }

    func testRecentRequestShapeAndReply() async throws {
        StubProtocol.status = 200
        StubProtocol.reply = Data(#"{"items":[{"key":"who:p_lin_17","kind":"who","title":"Lin"}]}"#.utf8)
        URLProtocol.registerClass(StubProtocol.self)
        defer { URLProtocol.unregisterClass(StubProtocol.self) }
        let api = KinAPI(baseURL: URL(string: "http://kin.test")!, token: "tok", apiKey: nil)
        let items = try await api.explainRecent(callId: 12)
        XCTAssertEqual(items.map(\.key), ["who:p_lin_17"])
        let req = try XCTUnwrap(StubProtocol.last)
        XCTAssertEqual(req.httpMethod, "POST")
        XCTAssertEqual(req.url?.path, "/api/calls/12/explain")
        XCTAssertEqual(req.value(forHTTPHeaderField: "X-KIN-User"), "tok")
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(StubProtocol.lastBody)) as? [String: Any])
        XCTAssertTrue(json["text"] is NSNull, "text is sent as null, not dropped")
        XCTAssertEqual(json["recent"] as? Bool, true)
        XCTAssertEqual(json.count, 2)
    }

    func testTwistCardTakesTheCardSlotLikeATap() throws {
        let waiting = try XCTUnwrap(explainStarted(WorldState(), term: recentAsk))
        XCTAssertNil(explainStarted(waiting, term: recentAsk), "a second twist while waiting does not send again")
        let out = recentExplained(waiting, items: [lin], now: t0)
        XCTAssertEqual(slots(out.rail).card?.key, "who:p_lin_17")
        XCTAssertTrue(out.explaining.isEmpty)
    }

    func testNothingClearShowsNothing() throws {
        let out = recentExplained(try XCTUnwrap(explainStarted(WorldState(), term: recentAsk)), items: [], now: t0)
        XCTAssertTrue(out.rail.isEmpty)
        XCTAssertNil(out.hint, "no hint line: there is no word to name, the haptic says it")
        XCTAssertTrue(out.explaining.isEmpty, "the next twist can ask again")
    }

    func testFailureIsShown() throws {
        let out = recentFailed(try XCTUnwrap(explainStarted(WorldState(), term: recentAsk)), message: "timed out")
        XCTAssertEqual(out.error, "Could not tell what this is about: timed out")
        XCTAssertTrue(out.explaining.isEmpty)
    }
}
