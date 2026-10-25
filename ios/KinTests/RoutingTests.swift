import XCTest
@testable import Kin

final class RoutingTests: XCTestCase {
    func testMyKinVoicePlays() {
        XCTAssertEqual(routeTrack(name: "kin-to-p3", participantIdentity: "kin", me: "p3", kind: .audio), .kinVoice)
    }

    func testOtherListenersKinVoiceIgnored() {
        XCTAssertEqual(routeTrack(name: "kin-to-p5", participantIdentity: "kin", me: "p3", kind: .audio), .ignore)
    }

    func testKinToTrackFromAPeerIsIgnored() {
        XCTAssertEqual(routeTrack(name: "kin-to-p3", participantIdentity: "p5", me: "p3", kind: .audio), .ignore)
    }

    func testPeerAudioAndVideo() {
        XCTAssertEqual(routeTrack(name: "microphone", participantIdentity: "p5", me: "p3", kind: .audio), .peerAudio)
        XCTAssertEqual(routeTrack(name: "camera", participantIdentity: "p5", me: "p3", kind: .video), .peerVideo)
        XCTAssertEqual(routeTrack(name: "", participantIdentity: "p7", me: "p3", kind: .video), .peerVideo)
    }

    func testAgentVideoAndOtherAgentAudioIgnored() {
        XCTAssertEqual(routeTrack(name: "avatar", participantIdentity: "kin", me: "p3", kind: .video), .ignore)
        XCTAssertEqual(routeTrack(name: "kin-to-p3", participantIdentity: "kin", me: "p3", kind: .video), .ignore)
        XCTAssertEqual(routeTrack(name: "chime", participantIdentity: "kin", me: "p3", kind: .audio), .ignore)
    }

    func testOwnTracksIgnored() {
        XCTAssertEqual(routeTrack(name: "microphone", participantIdentity: "p3", me: "p3", kind: .audio), .ignore)
    }

    func testIdentityPrefixesDoNotMatch() {
        XCTAssertEqual(routeTrack(name: "kin-to-p30", participantIdentity: "kin", me: "p3", kind: .audio), .ignore)
        XCTAssertEqual(routeTrack(name: "kin-to-p3", participantIdentity: "kin", me: "p30", kind: .audio), .ignore)
    }

    func testKinDataOnlyFromAgentOrServer() {
        XCTAssertTrue(acceptsKinData(topic: "kin", sender: "kin"))
        XCTAssertTrue(acceptsKinData(topic: "kin", sender: nil))
        XCTAssertFalse(acceptsKinData(topic: "kin", sender: "p5"))
        XCTAssertFalse(acceptsKinData(topic: "chat", sender: "kin"))
    }

    private func start(_ id: Int) -> KinWorldMsg { .audioStart(AudioStart(utteranceId: id, lang: "en")) }
    private func end(_ id: Int) -> KinWorldMsg { .audioEnd(AudioEnd(utteranceId: id)) }

    func testNoDuckWhenVoiceOff() {
        XCTAssertEqual(speakingUtterances(after: start(1), voiceOn: false, current: []), [])
    }

    func testDuckAndUnduck() {
        let s = speakingUtterances(after: start(1), voiceOn: true, current: [])
        XCTAssertEqual(s, [1])
        XCTAssertEqual(speakingUtterances(after: end(1), voiceOn: true, current: s), [])
        XCTAssertEqual(peerVolume(kinSpeaking: true), 0.25)
        XCTAssertEqual(peerVolume(kinSpeaking: false), 1.0)
    }

    func testOverlapUnducksAfterLastEnd() {
        var s: Set<Int> = []
        for m in [start(1), start(2), end(1)] { s = speakingUtterances(after: m, voiceOn: true, current: s) }
        XCTAssertEqual(s, [2])
        XCTAssertEqual(speakingUtterances(after: end(2), voiceOn: true, current: s), [])
    }
}
