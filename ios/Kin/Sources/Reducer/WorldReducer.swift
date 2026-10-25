import Foundation

// The call screen's state, built only from `kin` messages (docs/ARCHITECTURE.md 9.1) by a pure reducer. Time is a
// parameter everywhere, so tests drive lifetimes with fixed dates.

/// One card on the rail. `born` restarts when a touch ends, so a card never expires while (or right after) it is used.
struct RailCard: Equatable, Identifiable {
    enum Content: Equatable {
        case glance(GlanceItem, body: String)  // body separate: glance_update swaps it
        case culture(PragmaticsCard)
    }
    let key: String
    var content: Content
    var born: Date
    var touched = false

    var id: String { key }
    var kind: String {
        switch content {
        case .glance(let g, _): return g.kind
        case .culture: return "culture"
        }
    }
    /// Asks wait for an answer, so the rail cap never evicts them.
    var isAsk: Bool { kind == "ask" }
}

struct Caption: Equatable {
    let speaker: String          // display name
    let text: String             // in my language (translation, or src_text when we share a language)
    let isPartial: Bool
    let spans: [String: GroundedSpan]  // node_id -> how that name was grounded for me
    var original: String? = nil  // the speaker's own words, shown small above a translated line
    var utteranceId: Int? = nil  // sent with a tap-to-explain request
    var lang: String? = nil      // speaker's language
    var targetLang: String? = nil
    var speakerIdentity: String? = nil  // set on partials, so one can be dropped when its speaker leaves
}

struct WorldState: Equatable {
    var participants: [Participant] = []
    /// The latest line I can read. It changes only when a final lands, so the big line never jitters.
    var caption: Caption?
    /// The line before `caption` (hidden on screen while a card is up).
    var previous: Caption?
    /// The other person's live words, in their language, while they are still talking. Cleared by their final.
    var partial: Caption?
    /// Words I tapped and are waiting on (tap-to-explain), so a second tap does not send twice.
    var explaining: Set<String> = []
    /// One quiet line after a tap that found nothing ("Nothing to explain for X"), with when it was set.
    var hint: String?
    var hintAt: Date?
    /// Names and terms KIN grounded or carded this call; they stay tappable in later captions.
    var known: Set<String> = []
    var rail: [RailCard] = []         // newest first
    var dismissed: Set<String> = []   // keys I answered or dismissed; never shown again this call
    var status: String?               // asr state when not ok
    var error: String?

    static let railCap = 4
    /// Seconds a card stays when nobody touches it. Unknown kinds use `defaultLifetime`.
    static let lifetimes: [String: TimeInterval] = [
        "who": 20, "what": 20, "bridge": 30, "storyline": 30, "ask": 60, "culture": 25,
    ]
    static let defaultLifetime: TimeInterval = 20
    static let hintLifetime: TimeInterval = 4

    func name(of identity: String) -> String {
        participants.first { $0.identity == identity }?.name ?? identity
    }
}

/// Folds one server message into the state. `me` is my LiveKit identity.
func reduce(_ state: WorldState, _ msg: KinWorldMsg, me: String, now: Date) -> WorldState {
    var s = expire(state, now: now)
    switch msg {
    case .joined(let j):
        s.participants = j.participants
    case .participants(let p):
        s.participants = p.participants
        // Their final will never come, so live words from someone who left would keep their typing dots.
        if let id = s.partial?.speakerIdentity, !p.participants.contains(where: { $0.identity == id }) { s.partial = nil }
    case .kinStatus(let st):
        // ponytail: CallController owns KIN on/paused (REST reply + kin_status); one source for the screen. The
        // server drops speech while paused, so a half line from before the pause would wait for a final that never comes.
        // The paused screen removes every card, so a finger on one never lifts on it; release it here, or it would hold
        // its slot (and dodge the rail cap) for the rest of the call.
        if !st.on {
            s.partial = nil
            for card in s.rail where card.touched { s = touch(s, key: card.key, touching: false, now: now) }
        }
    case .partial(let p):
        guard p.speaker != me, !p.text.isEmpty else { break }
        s.partial = Caption(speaker: s.name(of: p.speaker), text: p.text, isPartial: true, spans: [:], lang: p.lang,
                            speakerIdentity: p.speaker)
    case .transcript(let t):
        guard t.speakerIdentity != me else { break }  // my own words are not captioned back to me
        var spans: [String: GroundedSpan] = [:]
        for span in t.groundedSpans ?? [] {
            if let id = span.nodeId { spans[id] = span }
            // source is in the speaker's words (the original line), rendered in mine (the translated line)
            s.known.formUnion([span.source, span.rendered].filter { !$0.isEmpty })
        }
        if s.caption != nil { s.previous = s.caption }
        s.caption = Caption(speaker: s.name(of: t.speakerIdentity), text: t.translation ?? t.srcText,
                            isPartial: false, spans: spans, original: t.translation == nil ? nil : t.srcText,
                            utteranceId: t.utteranceId, lang: t.srcLang, targetLang: t.targetLang)
        if s.partial?.speaker == s.caption?.speaker { s.partial = nil }
        s.error = nil  // a good transcript means the pipeline recovered
        s = addCulture(s, t.pragmaticsCards ?? [], utterance: t.utteranceId, now: now)
    case .enrich(let e):
        s = addCulture(s, e.pragmaticsCards, utterance: e.utteranceId, now: now)
    case .glance(let g):
        guard g.speaker != me else { break }  // the speaker never gets cards about their own words
        for item in g.items {
            s = add(s, RailCard(key: item.key, content: .glance(item, body: item.body), born: now))
            if item.kind != "bridge" { s.known.formUnion([item.title, item.native, item.term].filter { !$0.isEmpty }) }
        }
    case .glanceRetract(let r):
        s.rail.removeAll { r.keys.contains($0.key) }
    case .glanceUpdate(let u):
        s.rail = s.rail.map { card in
            guard card.key == u.key, case .glance(let g, _) = card.content else { return card }
            var c = card
            c.content = .glance(g, body: u.body)
            return c
        }
    case .status(let st):
        s.status = st.asr == "ok" ? nil : (st.detail?.isEmpty == false ? st.detail : st.asr)
        if st.asr == "ok" { s.error = nil }
    case .error(let e):
        s.error = e.message?.isEmpty == false ? e.message : "KIN \(e.stage) error"
    case .audioStart, .audioEnd, .latency, .unknown:
        break
    }
    return s
}

/// Drops untouched cards past their lifetime. Call it on a timer too, not only when messages arrive.
func expire(_ state: WorldState, now: Date) -> WorldState {
    var s = state
    if let at = s.hintAt, now.timeIntervalSince(at) > WorldState.hintLifetime { s.hint = nil; s.hintAt = nil }
    s.rail.removeAll { card in
        !card.touched && now.timeIntervalSince(card.born) > (WorldState.lifetimes[card.kind] ?? WorldState.defaultLifetime)
    }
    return s
}

/// A touch holds the card; releasing restarts its lifetime from `now`.
func touch(_ state: WorldState, key: String, touching: Bool, now: Date) -> WorldState {
    var s = state
    s.rail = s.rail.map { card in
        guard card.key == key else { return card }
        var c = card
        c.touched = touching
        if !touching { c.born = now }
        return c
    }
    return s
}

/// The user acted on a card (I know, dismiss, placed, not now): remove it and never show that key again.
func remove(_ state: WorldState, key: String) -> WorldState {
    var s = state
    s.rail.removeAll { $0.key == key }
    s.dismissed.insert(key)
    return s
}

/// Dedupe by key (a repeat replaces the card in place, keeping its age), newest first, then the cap.
func add(_ state: WorldState, _ card: RailCard) -> WorldState {
    var s = state
    guard !s.dismissed.contains(card.key) else { return s }
    if let i = s.rail.firstIndex(where: { $0.key == card.key }) {
        s.rail[i].content = card.content
        return s
    }
    s.rail.insert(card, at: 0)
    while s.rail.count > WorldState.railCap {
        // Evict the oldest card that is not an open ask; when every card is an ask, the oldest ask. A card under a
        // finger is never the one evicted.
        let victim = s.rail.lastIndex { !$0.isAsk && !$0.touched } ?? s.rail.lastIndex { !$0.touched } ?? s.rail.count - 1
        s.rail.remove(at: victim)
    }
    return s
}

private func addCulture(_ state: WorldState, _ cards: [PragmaticsCard], utterance: Int, now: Date) -> WorldState {
    var s = state
    for (i, c) in cards.enumerated() where !(c.meaning ?? "").isEmpty {
        s = add(s, RailCard(key: "culture:\(utterance):\(i)", content: .culture(c), born: now))
    }
    return s
}
