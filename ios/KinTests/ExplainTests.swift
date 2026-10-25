import XCTest
@testable import Kin

/// Tap-to-explain (ARCHITECTURE Amendment 5) at the state level, plus the request KinAPI.explain sends, against a
/// stubbed URLProtocol (no network).
@MainActor
final class ExplainTests: XCTestCase {
    let t0 = Date(timeIntervalSince1970: 2_000_000)

    private func item(_ json: String) -> GlanceItem { try! JSONDecoder().decode(GlanceItem.self, from: Data(json.utf8)) }

    private var lin: GlanceItem {
        item(#"{"key":"who:p_lin_17","kind":"who","title":"Lin","native":"林","body":"Mei's friend from the Fudan climbing wall, first mentioned Sep 14","node_id":"p_lin_17","gap":"reminder"}"#)
    }
    private var ask: GlanceItem {
        item(#"{"key":"ask:xiao wang","kind":"ask","title":"Xiao Wang","term":"Xiao Wang","suggestions":[{"owner":"p_mei_5","relation":"friend","label":"Mei's friend"}]}"#)
    }

    func testTappedCardTakesTheCardSlot() throws {
        var s = WorldState()
        s.rail = [RailCard(key: "story:3", content: .glance(item(#"{"key":"story:3","kind":"storyline","title":"t"}"#), body: ""), born: t0)]
        let waiting = try XCTUnwrap(explainStarted(s, term: "Lin"))
        XCTAssertNil(explainStarted(waiting, term: "Lin"), "a second tap on the same word does not send again")
        let out = explained(waiting, term: "Lin", items: [lin], now: t0)
        XCTAssertEqual(slots(out.rail).card?.key, "who:p_lin_17")
        XCTAssertTrue(out.explaining.isEmpty)
        XCTAssertEqual(triggerTerms(slots(out.rail).card), ["Lin", "林"])
    }

    func testTapBringsBackADismissedCard() {
        var s = remove(WorldState(), key: "who:p_lin_17")
        s = explained(explainStarted(s, term: "Lin")!, term: "Lin", items: [lin], now: t0)
        XCTAssertEqual(s.rail.map(\.key), ["who:p_lin_17"], "asking is explicit, so an earlier dismiss does not hide it")
        XCTAssertFalse(s.dismissed.contains("who:p_lin_17"))
    }

    func testTapOnACardAlreadyOnTheRailMovesItToTheFront() {
        var s = WorldState()
        s = Kin.add(s, RailCard(key: "who:p_lin_17", content: .glance(lin, body: lin.body), born: t0))
        s = Kin.add(s, RailCard(key: "story:3", content: .glance(item(#"{"key":"story:3","kind":"storyline","title":"t"}"#), body: ""), born: t0))
        s = explained(s, term: "Lin", items: [lin], now: t0.addingTimeInterval(5))
        XCTAssertEqual(s.rail.map(\.key), ["who:p_lin_17", "story:3"])
        XCTAssertEqual(s.rail.first?.born, t0.addingTimeInterval(5), "its lifetime restarts")
    }

    func testUnknownNameShowsTheAskCard() {
        let s = explained(WorldState(), term: "Xiao Wang", items: [ask], now: t0)
        let card = slots(s.rail).card
        XCTAssertEqual(card.map { CardRail.style(for: $0) }, .ask)
    }

    func testNothingFoundLeavesOneQuietHintThatExpires() {
        let s = explained(WorldState(), term: "climbing", items: [], now: t0)
        XCTAssertTrue(s.rail.isEmpty)
        XCTAssertEqual(s.hint, "Nothing to explain for \u{201C}climbing\u{201D}")
        XCTAssertNil(expire(s, now: t0.addingTimeInterval(WorldState.hintLifetime + 1)).hint)
    }

    func testFailureIsShownNotSwallowed() {
        let s = explainFailed(explainStarted(WorldState(), term: "Lin")!, term: "Lin", message: "KIN did not answer in time")
        XCTAssertEqual(s.error, "Could not explain Lin: KIN did not answer in time")
        XCTAssertTrue(s.explaining.isEmpty, "the word can be tapped again")
    }

    func testTappableTerms() {
        let known: Set<String> = ["Lin", "林", "Ravi"]
        XCTAssertEqual(tappableTerms(in: "Lin and I finally went climbing at Moganshan.", known: known), ["Moganshan", "Lin"])
        XCTAssertEqual(tappableTerms(in: "Ravi mama called. Adyar is far.", known: known.union(["Ravi mama"])), ["Ravi mama", "Ravi"],
                       "sentence-initial words are not names by capitalization alone; known terms are")
        XCTAssertEqual(tappableTerms(in: "我和林去攀岩了", known: known), [], "single CJK characters need a longer known form")
        XCTAssertEqual(tappableTerms(in: "我和小王去了", known: ["小王"]), ["小王"])
    }

    func testTappableTermsRespectWordsAndScripts() {
        XCTAssertEqual(tappableTerms(in: "she met linda there", known: ["Lin"]), [], "Lin is not inside Linda")
        XCTAssertEqual(tappableTerms(in: "she rode Lin's bike", known: ["Lin"]), ["Lin"], "possessive keeps the name only")
        XCTAssertEqual(tappableTerms(in: "and I'm here, OK, with KIN", known: []), [])
        XCTAssertEqual(tappableTerms(in: "\u{0E09}\u{0E31}\u{0E19}\u{0E44}\u{0E1B}\u{0E40}\u{0E0A}\u{0E35}\u{0E22}\u{0E07}\u{0E43}\u{0E2B}\u{0E21}\u{0E48}", known: ["\u{0E40}\u{0E0A}\u{0E35}\u{0E22}\u{0E07}\u{0E43}\u{0E2B}\u{0E21}\u{0E48}"]),
                       ["\u{0E40}\u{0E0A}\u{0E35}\u{0E22}\u{0E07}\u{0E43}\u{0E2B}\u{0E21}\u{0E48}"], "Thai has no spaces; a known term still matches")
        XCTAssertEqual(tappableTerms(in: "ரவி மாமா வந்தார்", known: ["ரவி மாமா"]), ["ரவி மாமா"])
        XCTAssertEqual(tappableTerms(in: "रवि मामा आए", known: ["रवि मामा"]), ["रवि मामा"])
        let styled = LiveCaptions.styled("Linda and Lin", tappable: ["Lin"], highlights: [])
        XCTAssertEqual(styled.runs.compactMap { $0.link.flatMap(ExplainLink.term) }, ["Lin"], "only the whole word is linked")
    }

    func testKnownTermsComeFromSpansAndCardsButNotBridges() {
        let msgs = [
            #"{"type":"transcript","call_id":1,"utterance_id":9,"speaker":"p_mei_5","speaker_identity":"p5","src_text":"我和小王去攀岩了","src_lang":"zh","target_lang":"en","translation":"Xiao Wang and I went climbing.","grounded_spans":[{"source":"小王","rendered":"Xiao Wang","node_id":"p_xw_9"}]}"#,
            #"{"type":"glance","speaker":"p5","items":[{"key":"who:p_lin_17","kind":"who","title":"Lin","native":"林","node_id":"p_lin_17","gap":"reminder"},{"key":"bridge:42","kind":"bridge","title":"You haven't told Mei","body":"you started bouldering","target":"p_mei_5","private":true}]}"#,
        ]
        let s = msgs.reduce(WorldState()) { reduce($0, KinWorldMsg.decode(Data($1.utf8)), me: "p3", now: t0) }
        XCTAssertTrue(s.known.isSuperset(of: ["小王", "Xiao Wang", "Lin", "林"]))
        XCTAssertFalse(s.known.contains("You haven't told Mei"), "bridges hold my private facts; never tappable")
        let c = s.caption!
        XCTAssertEqual(tappableTerms(in: c.original!, known: s.known), ["小王"], "the speaker's own line is tappable")
        XCTAssertEqual(tappableTerms(in: c.text, known: s.known), ["Xiao Wang"], "and so is the translated line")
    }

    func testTamilSpanIsTappableInTheOriginalLine() {
        let msg = #"{"type":"transcript","call_id":1,"utterance_id":3,"speaker":"p_paatti_2","speaker_identity":"p2","src_text":"ரவி மாமா வந்தார்","src_lang":"ta","target_lang":"en","translation":"Ravi mama came.","grounded_spans":[{"source":"ரவி மாமா","rendered":"Ravi mama","node_id":"p_ravi_4"}]}"#
        let s = reduce(WorldState(), KinWorldMsg.decode(Data(msg.utf8)), me: "p3", now: t0)
        XCTAssertEqual(tappableTerms(in: s.caption!.original!, known: s.known), ["ரவி மாமா"])
    }

    func testTappedCardLeavesTheBridgeSlotAlone() {
        var s = WorldState()
        s.rail = [RailCard(key: "bridge:42", content: .glance(item(#"{"key":"bridge:42","kind":"bridge","title":"b"}"#), body: ""), born: t0)]
        XCTAssertNil(slots(s.rail).card, "a bridge alone never fills the card slot")
        let out = explained(explainStarted(s, term: "Lin")!, term: "Lin", items: [lin], now: t0)
        XCTAssertEqual(slots(out.rail).card?.key, "who:p_lin_17")
        XCTAssertEqual(slots(out.rail).bridge?.key, "bridge:42")
    }

    func testMessagesShowsOnlyFactsFromTexts() throws {
        let json = #"{"about_me":[{"id":1,"text":"started bouldering","subject":"p_arjun_3","source_kind":"message"},{"id":2,"text":"likes tea","subject":"p_arjun_3","source_kind":"call"}],"i_said":[]}"#
        let facts = try JSONDecoder().decode(FactsOut.self, from: Data(json.utf8))
        XCTAssertEqual(MessagesScreen.fromTexts(facts).map(\.id), [1])
    }

    func testCaptionLinksRoundTrip() throws {
        let url = try XCTUnwrap(ExplainLink.url("Ravi mama"))
        XCTAssertEqual(ExplainLink.term(url), "Ravi mama")
        XCTAssertEqual(ExplainLink.term(try XCTUnwrap(ExplainLink.url("小王"))), "小王")
        XCTAssertNil(ExplainLink.term(URL(string: "https://example.com/Lin")!))
        let styled = LiveCaptions.styled("Ravi mama and Ravi", tappable: ["Ravi", "Ravi mama"], highlights: [])
        let links = styled.runs.compactMap { $0.link.flatMap(ExplainLink.term) }
        XCTAssertEqual(links, ["Ravi mama", "Ravi"], "the longer term wins its range; no double link")
    }

    func testExplainRequestShapeAndReply() async throws {
        StubProtocol.reply = Data(#"{"items":[{"key":"who:p_lin_17","kind":"who","title":"Lin","gap":"reminder"}]}"#.utf8)
        URLProtocol.registerClass(StubProtocol.self)
        defer { URLProtocol.unregisterClass(StubProtocol.self) }
        let api = KinAPI(baseURL: URL(string: "http://kin.test")!, token: "tok", apiKey: nil)
        let items = try await api.explain(callId: 12, text: "Lin", utteranceId: 91)
        XCTAssertEqual(items.map(\.key), ["who:p_lin_17"])
        let req = try XCTUnwrap(StubProtocol.last)
        XCTAssertEqual(req.httpMethod, "POST")
        XCTAssertEqual(req.url?.path, "/api/calls/12/explain")
        XCTAssertEqual(req.value(forHTTPHeaderField: "X-KIN-User"), "tok")
        let body = try XCTUnwrap(StubProtocol.lastBody)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(json["text"] as? String, "Lin")
        XCTAssertEqual(json["utterance_id"] as? Int, 91)

        let none = try JSONSerialization.jsonObject(with: JSONEncoder().encode(ExplainIn(text: "Lin", utteranceId: nil))) as? [String: Any]
        XCTAssertTrue(none?["utterance_id"] is NSNull, "utterance_id is sent as null, not dropped")
    }
}

/// Answers every request with `reply` and records it. URLSession moves the body to a stream, so it is read here.
final class StubProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var reply = Data()
    nonisolated(unsafe) static var last: URLRequest?
    nonisolated(unsafe) static var lastBody: Data?

    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "kin.test" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.last = request
        Self.lastBody = request.httpBody ?? request.httpBodyStream.map { stream in
            stream.open()
            defer { stream.close() }
            var data = Data()
            var buf = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable { let n = stream.read(&buf, maxLength: buf.count); if n <= 0 { break }; data.append(buf, count: n) }
            return data
        }
        let resp = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.reply)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
