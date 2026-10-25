import XCTest
@testable import Kin

/// Every server -> client example from docs/ARCHITECTURE.md 9.1, verbatim (the glance's `[GlanceItem]` placeholder is
/// filled with the GlanceItem example, comments removed).
final class ContractsDecodingTests: XCTestCase {
    private func msg(_ json: String) -> KinWorldMsg { KinWorldMsg.decode(Data(json.utf8)) }

    static let glanceItem = #"""
    {"key":"who:p_lin_17","kind":"who|what|term|saying|ask|bridge|storyline",
     "title":"Lin","native":"林","body":"Mei's friend from the Fudan climbing wall, first mentioned Sep 14",
     "category":"person","image_url":"","image_credit":"","source_url":"",
     "node_id":"p_lin_17","gap":"new|reminder",
     "term":"Lin","guess":"Lin","suggestions":[{"owner":"p_mei_5","relation":"friend","label":"Mei's friend"}],
     "target":"p_mei_5","private":true,
     "storyline_id":3,"states":[{"label":"applied","at":"2026-09-02","known":true},{"label":"second round","at":"2026-10-10","known":false}]}
    """#

    func testJoined() {
        guard case .joined(let j) = msg(#"""
        {"type":"joined","call_id":12,"identity":"p3","person":"p_arjun_3","name":"Arjun","lang":"en","role":"participant",
         "peer_present":true,"participants":[{"identity":"p5","person":"p_mei_5","name":"Mei","lang":"zh"}],
         "kin":{"on":true,"paused_by":null}}
        """#) else { return XCTFail("not joined") }
        XCTAssertEqual(j.callId, 12)
        XCTAssertEqual(j.participants.first?.lang, "zh")
        XCTAssertTrue(j.kin.on)
        XCTAssertNil(j.kin.pausedBy)
    }

    func testParticipants() {
        guard case .participants(let p) = msg(#"""
        {"type":"participants","participants":[{"identity":"p5","person":"p_mei_5","name":"Mei","lang":"zh"}]}
        """#) else { return XCTFail("not participants") }
        XCTAssertEqual(p.participants.map(\.identity), ["p5"])
    }

    func testKinStatus() {
        guard case .kinStatus(let s) = msg(#"""
        {"type":"kin_status","on":false,"paused_by":{"person":"p_priya_4","name":"Priya"}}
        """#) else { return XCTFail("not kin_status") }
        XCTAssertFalse(s.on)
        XCTAssertEqual(s.pausedBy?.name, "Priya")
    }

    func testPartial() {
        guard case .partial(let p) = msg(#"""
        {"type":"partial","speaker":"p5","person":"p_mei_5","role":"participant","lang":"zh","text":"我和林去"}
        """#) else { return XCTFail("not partial") }
        XCTAssertEqual(p.text, "我和林去")
    }

    func testGlance() {
        guard case .glance(let g) = msg(#"{"type":"glance","speaker":"p5","role":"participant","partial":true,"items":["#
            + Self.glanceItem + "]}") else { return XCTFail("not glance") }
        XCTAssertTrue(g.partial)
        let item = g.items[0]
        XCTAssertEqual(item.key, "who:p_lin_17")
        XCTAssertEqual(item.native, "林")
        XCTAssertEqual(item.nodeId, "p_lin_17")
        XCTAssertTrue(item.isPrivate)
        XCTAssertEqual(item.storylineId, 3)
        XCTAssertEqual(item.states.map(\.known), [true, false])
        XCTAssertEqual(item.suggestions.first?.label, "Mei's friend")
    }

    func testGlanceRetractAndUpdate() {
        guard case .glanceRetract(let r) = msg(#"{"type":"glance_retract","keys":["who:p_lin_17"]}"#)
        else { return XCTFail("not retract") }
        XCTAssertEqual(r.keys, ["who:p_lin_17"])
        guard case .glanceUpdate(let u) = msg(#"{"type":"glance_update","key":"who:p_lin_17","body":"梅在复旦攀岩墙认识的朋友"}"#)
        else { return XCTFail("not update") }
        XCTAssertEqual(u.body, "梅在复旦攀岩墙认识的朋友")
    }

    func testTranscript() {
        guard case .transcript(let t) = msg(#"""
        {"type":"transcript","call_id":12,"utterance_id":91,"speaker":"p_mei_5","speaker_identity":"p5","role":"participant",
         "listener":"p_arjun_3","src_text":"我和林去攀岩了","src_lang":"zh","src_lang_tags":[],"target_lang":"en","heritage_lang":"zh",
         "translation":"I went climbing with Lin.",
         "grounded_spans":[{"source":"林","rendered":"Mei's friend Lin (from the Fudan climbing wall)","node_id":"p_lin_17"}],
         "pragmatics_cards":[],"passthrough":[],"confidence":0.9,
         "linker_spans":[{"start":2,"end":3,"source":"林","node_id":"p_lin_17","type":"person","confidence":0.95,"rendered":"...","candidates":[],"method":"alias"}],
         "latencies":{"scan_ms":0.4,"a_ms":1850,"mt_ms":1862},"error":null}
        """#) else { return XCTFail("not transcript") }
        XCTAssertEqual(t.utteranceId, 91)
        XCTAssertEqual(t.translation, "I went climbing with Lin.")
        XCTAssertEqual(t.groundedSpans?.first?.nodeId, "p_lin_17")
        XCTAssertEqual(t.linkerSpans?.first?.start, 2)
        XCTAssertEqual(t.latencies?["a_ms"], 1850)
    }

    func testTranscriptSameLanguage() {
        guard case .transcript(let t) = msg(#"""
        {"type":"transcript","call_id":12,"utterance_id":92,"speaker":"p_mei_5","speaker_identity":"p5","role":"participant",
         "listener":"p_lin_17","src_text":"好","src_lang":"zh","src_lang_tags":[],"target_lang":"zh","heritage_lang":"zh",
         "translation":null,"grounded_spans":[],"pragmatics_cards":[],"passthrough":[],"confidence":0.9,
         "linker_spans":[],"latencies":{},"error":null}
        """#) else { return XCTFail("not transcript") }
        XCTAssertNil(t.translation)
    }

    func testKnownTypeWithBrokenBodyDegrades() {
        XCTAssertEqual(msg(#"{"type":"partial"}"#), .unknown("malformed"))
    }

    func testEnrich() {
        guard case .enrich(let e) = msg(#"{"type":"enrich","utterance_id":91,"pragmatics_cards":[],"b_ms":2100}"#)
        else { return XCTFail("not enrich") }
        XCTAssertEqual(e.bMs, 2100)
    }

    func testAudioStartEnd() {
        XCTAssertEqual(msg(#"{"type":"audio_start","utterance_id":91,"lang":"en"}"#),
                       .audioStart(AudioStart(utteranceId: 91, lang: "en")))
        XCTAssertEqual(msg(#"{"type":"audio_end","utterance_id":91}"#), .audioEnd(AudioEnd(utteranceId: 91)))
    }

    func testLatency() {
        guard case .latency(let l) = msg(#"""
        {"type":"latency","utterance_id":91,"latencies":{"tts_first_byte_ms":310,"cards_ms":1.2,"total_ms":2400}}
        """#) else { return XCTFail("not latency") }
        XCTAssertEqual(l.latencies["cards_ms"], 1.2)
    }

    func testStatusAndError() {
        guard case .status(let s) = msg(#"{"type":"status","asr":"ok|unavailable|ended","detail":""}"#)
        else { return XCTFail("not status") }
        XCTAssertEqual(s.detail, "")
        guard case .error(let e) = msg(#"{"type":"error","stage":"mt|tts|pipeline","message":""}"#)
        else { return XCTFail("not error") }
        XCTAssertEqual(e.stage, "mt|tts|pipeline")
    }

    func testJoinWorldCarriesTheInvite() throws {
        let out = try JSONDecoder().decode(JoinWorldOut.self, from: Data(#"""
        {"call_id":12,"room":"kin-call-12","token":"jwt","url":"ws://localhost:7880","identity":"p3","person":"p_arjun_3",
         "name":"Arjun","lang":"en","participants":[],"invite":"0123456789abcdef"}
        """#.utf8))
        XCTAssertEqual(out.invite, "0123456789abcdef")
        let old = try JSONDecoder().decode(JoinWorldOut.self, from: Data(#"""
        {"call_id":12,"room":"r","token":"t","url":"u","identity":"p3","person":"p","name":"A","lang":"en","participants":[]}
        """#.utf8))
        XCTAssertNil(old.invite)
        let body = try JSONSerialization.jsonObject(with: JSONEncoder().encode(JoinWorldIn(callId: 12, invite: "c"))) as? [String: Any]
        XCTAssertEqual(body?["call_id"] as? Int, 12)
        XCTAssertEqual(body?["invite"] as? String, "c")
    }

    func testWorldStorylineOwnerIsOptional() throws {
        let s = try JSONDecoder().decode([WorldStoryline].self, from: Data(#"""
        [{"id":1,"title":"job search","status":"active","states":[],"owner":"p_mei_5"},
         {"id":2,"title":"move","status":"active"}]
        """#.utf8))
        XCTAssertEqual(s.map(\.owner), ["p_mei_5", nil])
    }

    func testUnknownType() {
        XCTAssertEqual(msg(#"{"type":"hologram","x":1}"#), .unknown("hologram"))
        XCTAssertEqual(msg("not json"), .unknown("malformed"))
    }
}
