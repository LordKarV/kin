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
}

struct WorldState: Equatable {
    var participants: [Participant] = []
    var caption: Caption?
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
    case .kinStatus:
        break  // ponytail: CallController owns KIN on/paused (REST reply + kin_status); one source for the screen
    case .partial(let p):
        guard p.speaker != me, !p.text.isEmpty else { break }
        s.caption = Caption(speaker: s.name(of: p.speaker), text: p.text, isPartial: true, spans: [:])
    case .transcript(let t):
        guard t.speakerIdentity != me else { break }  // my own words are not captioned back to me
        var spans: [String: GroundedSpan] = [:]
        for span in t.groundedSpans ?? [] { if let id = span.nodeId { spans[id] = span } }
        s.caption = Caption(speaker: s.name(of: t.speakerIdentity), text: t.translation ?? t.srcText,
                            isPartial: false, spans: spans)
        s.error = nil  // a good transcript means the pipeline recovered
        s = addCulture(s, t.pragmaticsCards ?? [], utterance: t.utteranceId, now: now)
    case .enrich(let e):
        s = addCulture(s, e.pragmaticsCards, utterance: e.utteranceId, now: now)
    case .glance(let g):
        guard g.speaker != me else { break }  // the speaker never gets cards about their own words
        for item in g.items { s = add(s, RailCard(key: item.key, content: .glance(item, body: item.body), born: now)) }
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
private func add(_ state: WorldState, _ card: RailCard) -> WorldState {
    var s = state
    guard !s.dismissed.contains(card.key) else { return s }
    if let i = s.rail.firstIndex(where: { $0.key == card.key }) {
        s.rail[i].content = card.content
        return s
    }
    s.rail.insert(card, at: 0)
    while s.rail.count > WorldState.railCap {
        // Evict the oldest card that is not an open ask; only when every card is an ask, the oldest ask.
        let victim = s.rail.lastIndex { !$0.isAsk } ?? s.rail.count - 1
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
