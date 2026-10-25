import Foundation

// Tap-to-explain (docs/ARCHITECTURE.md Amendment 5) and the call screen's one-card layout rule
// (docs/collab/design-notes.md, layout rule 3), as pure functions over WorldState.

/// A tap was sent for `term`. Returns nil when the same word is already waiting (no double send).
func explainStarted(_ state: WorldState, term: String) -> WorldState? {
    guard !state.explaining.contains(term) else { return nil }
    var s = state
    s.explaining.insert(term)
    s.hint = nil
    s.hintAt = nil
    return s
}

/// The server answered a tap. Each item goes to the front of the rail (so it takes the card slot), even when the
/// user had dismissed that key earlier: asking is an explicit request. No items: one quiet hint line.
func explained(_ state: WorldState, term: String, items: [GlanceItem], now: Date) -> WorldState {
    var s = state
    s.explaining.remove(term)
    guard !items.isEmpty else {
        s.hint = "Nothing to explain for \u{201C}\(term)\u{201D}"
        s.hintAt = now
        return s
    }
    for item in items.reversed() {  // the first item ends up newest
        s.dismissed.remove(item.key)
        s.rail.removeAll { $0.key == item.key }
        s = add(s, RailCard(key: item.key, content: .glance(item, body: item.body), born: now))
    }
    return s
}

func explainFailed(_ state: WorldState, term: String, message: String) -> WorldState {
    var s = state
    s.explaining.remove(term)
    s.error = "Could not explain \(term): \(message)"
    return s
}

/// The double twist's slot in `explaining` (Amendment 7), so a second twist while one is waiting does not send again.
/// Starts with a control character, so no caption word can collide with it. Start it with `explainStarted`.
let recentAsk = "\u{1}recent"

/// The server answered a twist. A card takes the slot exactly like a tap; nothing found shows nothing (the phone
/// plays a soft haptic instead of a hint line, since there is no word to name).
func recentExplained(_ state: WorldState, items: [GlanceItem], now: Date) -> WorldState {
    guard items.isEmpty else { return explained(state, term: recentAsk, items: items, now: now) }
    var s = state
    s.explaining.remove(recentAsk)
    return s
}

func recentFailed(_ state: WorldState, message: String) -> WorldState {
    var s = state
    s.explaining.remove(recentAsk)
    s.error = "Could not tell what this is about: \(message)"
    return s
}

/// What the call screen shows: one card about their world (the newest that is not a bridge) and at most one bridge.
/// A card under a finger keeps its slot; newer cards wait behind it until the touch ends.
func slots(_ rail: [RailCard]) -> (card: RailCard?, bridge: RailCard?) {
    func pick(_ cards: [RailCard]) -> RailCard? { cards.first { $0.touched } ?? cards.first }
    return (pick(rail.filter { $0.kind != "bridge" }), pick(rail.filter { $0.kind == "bridge" }))
}

/// Words in the card currently on screen: tinted and dotted-underlined in the caption so it is clear why it showed.
func triggerTerms(_ card: RailCard?) -> [String] {
    guard let card, case .glance(let g, _) = card.content else { return [] }
    return [g.title, g.native, g.term].filter { !$0.isEmpty }
}

/// Every name, place or term in the line that can be tapped: words KIN has grounded or carded this call, plus
/// capitalized Latin words that are not just the first word of a sentence. Longest first, so "Ravi mama" wins
/// over "Ravi". ponytail: the capitalization rule misses lowercase terms in Latin text ("murukku") until KIN has
/// carded them once; a server-side term list would close that.
func tappableTerms(in text: String, known: Set<String>) -> [String] {
    var found = Set(known.filter { $0.count > 1 && !termRanges(of: $0, in: text).isEmpty })
    let words = text.split(whereSeparator: { $0.isWhitespace })
    var sentenceStart = true
    for raw in words {
        var word = raw.trimmingCharacters(in: .punctuationCharacters)
        for suffix in ["'s", "\u{2019}s"] where word.hasSuffix(suffix) { word = String(word.dropLast(2)) }
        let contraction = word.first == "I" && word.contains { $0 == "'" || $0 == "\u{2019}" }  // I'm, I've
        let shortCaps = word.count <= 3 && word == word.uppercased()  // OK, KIN, TV
        let covered = found.contains { $0.contains(word) }  // "Wang" inside a known "Xiao Wang"
        if let first = word.unicodeScalars.first, word.count > 1, !sentenceStart, !contraction, !shortCaps, !covered,
           CharacterSet.uppercaseLetters.contains(first), first.isASCII {
            found.insert(word)
        }
        sentenceStart = raw.last.map { ".!?".contains($0) } ?? false
    }
    return found.sorted { $0.count != $1.count ? $0.count > $1.count : $0 < $1 }
}

/// Where `term` occurs in `text`. A term with Latin letters must stand as a whole word ("Lin" is not in "Linda");
/// CJK and Thai have no spaces, so they match as plain substrings.
func termRanges(of term: String, in text: String) -> [Range<String.Index>] {
    guard !term.isEmpty else { return [] }
    let latin = term.unicodeScalars.contains { $0.isASCII && CharacterSet.letters.contains($0) }
    func wordChar(_ c: Character) -> Bool { c.isLetter || c.isNumber }
    var out: [Range<String.Index>] = []
    var from = text.startIndex
    while let r = text.range(of: term, range: from..<text.endIndex) {
        from = r.upperBound
        if latin {
            if r.lowerBound > text.startIndex, wordChar(text[text.index(before: r.lowerBound)]) { continue }
            if r.upperBound < text.endIndex, wordChar(text[r.upperBound]) { continue }
        }
        out.append(r)
    }
    return out
}

/// Caption words travel to the tap handler as `kin-explain:<term>` links.
enum ExplainLink {
    static let scheme = "kin-explain"

    static func url(_ term: String) -> URL? {
        var c = URLComponents()
        c.scheme = scheme
        c.path = term
        return c.url
    }

    static func term(_ url: URL) -> String? {
        guard url.scheme == scheme else { return nil }
        let c = URLComponents(url: url, resolvingAgainstBaseURL: false)
        return c?.path.isEmpty == false ? c?.path : nil
    }
}
