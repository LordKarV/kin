import SwiftUI
import XCTest
@testable import Kin

@MainActor
final class WorldReducerTests: XCTestCase {
    let me = "p3"
    let t0 = Date(timeIntervalSince1970: 1_000_000)

    private func msg(_ json: String) -> KinWorldMsg {
        let m = KinWorldMsg.decode(Data(json.utf8))
        if case .unknown(let t) = m { XCTFail("did not decode (\(t)): \(json)") }
        return m
    }

    private func run(_ jsons: [String], from state: WorldState = WorldState(), at now: Date? = nil) -> WorldState {
        jsons.reduce(state) { reduce($0, msg($1), me: me, now: now ?? t0) }
    }

    private func glance(_ item: String, speaker: String = "p5") -> String {
        #"{"type":"glance","speaker":"\#(speaker)","items":[\#(item)]}"#
    }

    private let lin = #"{"key":"who:p_lin_17","kind":"who","title":"Lin","native":"林","body":"Mei's friend from the Fudan climbing wall","gap":"reminder"}"#

    private func ask(_ n: Int) -> String {
        #"{"key":"ask:x\#(n)","kind":"ask","term":"X\#(n)","suggestions":[{"owner":"p_mei_5","relation":"friend","label":"Mei's friend"}]}"#
    }

    private func who(_ n: Int) -> String { #"{"key":"who:p\#(n)","kind":"who","title":"P\#(n)","body":"b","gap":"new"}"# }

    func testReminderCardAppears() {
        let s = run([glance(lin)])
        XCTAssertEqual(s.rail.map(\.key), ["who:p_lin_17"])
        guard case .glance(let g, let body) = s.rail[0].content else { return XCTFail("not a glance card") }
        XCTAssertEqual(g.gap, "reminder")
        XCTAssertEqual(body, "Mei's friend from the Fudan climbing wall")
    }

    func testOwnWordsGetNoCards() {
        XCTAssertTrue(run([glance(lin, speaker: "p3")]).rail.isEmpty)
    }

    func testRetractRemovesCard() {
        let s = run([glance(lin), #"{"type":"glance_retract","keys":["who:p_lin_17"]}"#])
        XCTAssertTrue(s.rail.isEmpty)
    }

    func testGlanceUpdateSwapsBody() {
        let s = run([glance(lin), #"{"type":"glance_update","key":"who:p_lin_17","body":"梅在复旦攀岩墙认识的朋友"}"#])
        guard case .glance(_, let body) = s.rail[0].content else { return XCTFail("not a glance card") }
        XCTAssertEqual(body, "梅在复旦攀岩墙认识的朋友")
    }

    func testDuplicateKeyIsDeduped() {
        XCTAssertEqual(run([glance(lin), glance(lin)]).rail.count, 1)
    }

    func testBridgeIsPrivate() {
        let s = run([glance(#"{"key":"bridge:42","kind":"bridge","title":"You haven't told Mei","body":"you started bouldering","target":"p_mei_5","private":true}"#)])
        XCTAssertEqual(CardRail.style(for: s.rail[0]), .bridge)  // drawn as the private chip, not a plain card
        guard case .glance(let g, let body) = s.rail[0].content else { return XCTFail("not a glance card") }
        XCTAssertTrue(g.isPrivate)
        let chip = BridgeChip(title: g.title, text: body, onDismiss: {})
        XCTAssertEqual(BridgeChip.label, "Only you")
        XCTAssertEqual(chip.line, "You haven't told Mei: you started bouldering")
        XCTAssertEqual(BridgeChip(title: "", text: body, onDismiss: {}).line, "you started bouldering")
    }

    func testCardStyles() {
        let s = run([glance(lin), glance(ask(1)), glance(#"{"key":"term:1","kind":"term","title":"Moganshan","body":"a mountain"}"#)])
        XCTAssertEqual(s.rail.map { CardRail.style(for: $0) }, [.culture, .ask, .who])
    }

    func testStorylineKeepsStates() {
        let s = run([glance(#"{"key":"story:3","kind":"storyline","title":"Mei's job search","storyline_id":3,"states":[{"label":"applied","at":"2026-09-02","known":true},{"label":"second round","at":"2026-10-10","known":false}]}"#)])
        guard case .glance(let g, _) = s.rail[0].content else { return XCTFail("not a glance card") }
        XCTAssertEqual(g.states.map(\.label), ["applied", "second round"])
        XCTAssertEqual(g.states.map(\.known), [true, false])
        XCTAssertEqual(StorylineCard.month("2026-10-10"), DateFormatter().shortMonthSymbols[9])
    }

    func testCaptionUsesTranslationElseSource() {
        let base = #""type":"transcript","call_id":1,"utterance_id":9,"speaker":"p_mei_5","speaker_identity":"p5","src_text":"我和林去攀岩了","src_lang":"zh","target_lang":"en""#
        let joined = #"{"type":"joined","call_id":1,"identity":"p3","person":"p_arjun_3","name":"Arjun","lang":"en","participants":[{"identity":"p5","person":"p_mei_5","name":"Mei","lang":"zh"}],"kin":{"on":true,"paused_by":null}}"#
        let translated = run([joined, "{\(base),\"translation\":\"I went climbing with Lin.\",\"grounded_spans\":[{\"source\":\"林\",\"rendered\":\"Mei's friend Lin\",\"node_id\":\"p_lin_17\"}]}"])
        XCTAssertEqual(translated.caption?.text, "I went climbing with Lin.")
        XCTAssertEqual(translated.caption?.speaker, "Mei")
        XCTAssertEqual(translated.caption?.spans["p_lin_17"]?.rendered, "Mei's friend Lin")
        let same = run(["{\(base),\"translation\":null}"])
        XCTAssertEqual(same.caption?.text, "我和林去攀岩了")
    }

    func testPartialThenOwnTranscriptKeepsPeerCaption() {
        let s = run([#"{"type":"partial","speaker":"p5","person":"p_mei_5","lang":"zh","text":"我和林"}"#,
                     #"{"type":"transcript","call_id":1,"utterance_id":10,"speaker":"p_arjun_3","speaker_identity":"p3","src_text":"nice","src_lang":"en","target_lang":"en","translation":null}"#])
        XCTAssertEqual(s.caption?.text, "我和林")
        XCTAssertEqual(s.caption?.isPartial, true)
    }

    func testKinStatusOffShowsPaused() throws {
        // The screen reads CallController.isPaused/pausedBy, which come straight from kin_status.
        guard case .kinStatus(let off) = msg(#"{"type":"kin_status","on":false,"paused_by":{"person":"p_mei_5","name":"Mei"}}"#)
        else { return XCTFail("not kin_status") }
        XCTAssertEqual(KinIndicator(on: off.on, pausedBy: off.pausedBy, myPerson: "p_arjun_3").text, "KIN paused by Mei")
        XCTAssertEqual(KinIndicator(on: off.on, pausedBy: off.pausedBy, myPerson: "p_mei_5").text, "You paused KIN")
        XCTAssertEqual(KinIndicator(on: false, pausedBy: nil, myPerson: "p_arjun_3").text, "KIN is paused")
        XCTAssertEqual(KinIndicator(on: true, pausedBy: nil, myPerson: "p_arjun_3").text, "KIN is on")
    }

    func testErrorClearsWhenPipelineRecovers() {
        let err = run([#"{"type":"error","stage":"pipeline","message":"ASR down"}"#, #"{"type":"status","asr":"unavailable"}"#])
        XCTAssertEqual(err.error, "ASR down")
        XCTAssertEqual(err.status, "unavailable")
        let ok = run([#"{"type":"status","asr":"ok"}"#], from: err)
        XCTAssertNil(ok.error)
        XCTAssertNil(ok.status)
        let base = #""type":"transcript","call_id":1,"utterance_id":9,"speaker":"p_mei_5","speaker_identity":"p5","src_text":"hi","src_lang":"en","target_lang":"en","translation":null"#
        XCTAssertNil(run(["{\(base)}"], from: err).error)
    }

    func testRailCapAllAsksEvictsOldestAsk() {
        let s = run((1...5).map { glance(ask($0)) })
        XCTAssertEqual(s.rail.map(\.key), ["ask:x5", "ask:x4", "ask:x3", "ask:x2"])
    }

    func testRailCapFullOfAsksDropsNewWhoCard() {
        // Open asks outrank a passing who card: with four asks waiting, the new who card is not shown.
        let s = run((1...4).map { glance(ask($0)) } + [glance(who(1))])
        XCTAssertEqual(s.rail.map(\.key), ["ask:x4", "ask:x3", "ask:x2", "ask:x1"])
    }

    func testRailCapKeepsOpenAsks() {
        let s = run([glance(ask(1)), glance(who(1)), glance(who(2)), glance(ask(2)), glance(who(3)), glance(who(4))])
        XCTAssertEqual(s.rail.count, WorldState.railCap)
        XCTAssertEqual(Set(s.rail.map(\.key)), ["ask:x1", "ask:x2", "who:p4", "who:p3"])
        XCTAssertEqual(s.rail.first?.key, "who:p4")  // newest first
    }

    func testCardsExpireUnlessTouched() {
        var s = run([glance(lin), glance(who(1))])
        s = touch(s, key: "who:p_lin_17", touching: true, now: t0)
        s = expire(s, now: t0.addingTimeInterval(60))
        XCTAssertEqual(s.rail.map(\.key), ["who:p_lin_17"])
        s = touch(s, key: "who:p_lin_17", touching: false, now: t0.addingTimeInterval(60))
        XCTAssertEqual(expire(s, now: t0.addingTimeInterval(70)).rail.count, 1)  // lifetime restarts on release
        XCTAssertTrue(expire(s, now: t0.addingTimeInterval(90)).rail.isEmpty)
    }

    func testRemovedKeyNeverReturns() {
        let s = remove(run([glance(lin)]), key: "who:p_lin_17")
        XCTAssertTrue(run([glance(lin)], from: s).rail.isEmpty)
    }

    func testEnrichAddsCultureCard() {
        let s = run([#"{"type":"enrich","utterance_id":9,"pragmatics_cards":[{"kind":"care","source":"你瘦了","literal":"you got thin","meaning":"A sign of care, not criticism"}]}"#])
        XCTAssertEqual(s.rail.first?.kind, "culture")
    }

    func testDemoDataHasTheThreeCardsAndACaption() {
        let s = CallDemo.state(now: t0)
        XCTAssertEqual(s.rail.map(\.key), ["who:p_lin_17", "bridge:42", "story:3"])
        XCTAssertEqual(s.caption?.text, "Lin and I finally did the Moganshan trip.")
    }
}

/// Renders the -demoCallScreen view in the host app's window and saves ios/screens/call-demo.png.
/// ponytail: stand-in for `simctl io screenshot` until App/KinApp.swift (2E) reads CallDemo.isRequested; delete then.
@MainActor
final class CallDemoScreenshotTests: XCTestCase {
    func testSaveDemoScreenshot() throws {
        // Writes into the source tree, so only on request: TEST_RUNNER_KIN_WRITE_SCREENSHOT=1 xcodebuild test ...
        try XCTSkipUnless(ProcessInfo.processInfo.environment["KIN_WRITE_SCREENSHOT"] == "1", "set KIN_WRITE_SCREENSHOT=1")
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        let window = UIWindow(windowScene: scene)
        window.overrideUserInterfaceStyle = .dark
        window.rootViewController = UIHostingController(rootView: CallDemo.view().preferredColorScheme(.dark))
        window.makeKeyAndVisible()
        RunLoop.main.run(until: Date().addingTimeInterval(1.0))
        let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
            window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
        }
        window.isHidden = true
        let out = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("screens/call-demo.png")
        try FileManager.default.createDirectory(at: out.deletingLastPathComponent(), withIntermediateDirectories: true)
        try XCTUnwrap(image.pngData()).write(to: out)
    }
}
