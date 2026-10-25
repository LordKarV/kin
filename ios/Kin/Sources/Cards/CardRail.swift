import SwiftUI

/// What the user did to a card. The call screen turns these into REST calls and reducer updates.
enum CardAction: Equatable {
    case know
    case dismiss
    case place(Suggestion)
    case touch(Bool)
}

/// Draws one rail card in the call screen's card slot. The screen shows one card about their world at a time plus
/// at most one bridge (`slots(_:)`); a newer card replaces the one on screen.
enum CardRail {
    /// Which component draws a card. Pure, so tests pin the kind-to-card mapping.
    enum Style: Equatable { case who, bridge, storyline, ask, culture }

    static func style(for card: RailCard) -> Style {
        switch card.kind {
        case "who", "what": return .who
        case "bridge": return .bridge
        case "storyline": return .storyline
        case "ask": return .ask
        default: return .culture  // culture, term, saying, and kinds this build does not know yet
        }
    }
}

struct CardView: View {
    let card: RailCard
    let speakerName: String
    let onAction: (RailCard, CardAction) -> Void

    var body: some View {
        content
            // A touch holds the card (it never vanishes under a finger); lifting restarts its lifetime.
            .onLongPressGesture(minimumDuration: 0.2, maximumDistance: 20, perform: {}) { onAction(card, .touch($0)) }
            .accessibilityAction(named: "I know this") { onAction(card, .know) }
            .accessibilityAction(named: "Dismiss") { onAction(card, .dismiss) }
    }

    @ViewBuilder private var content: some View {
        switch card.content {
        case .culture(let p):
            MeaningCard(card: p)
        case .glance(let g, let body):
            switch CardRail.style(for: card) {
            case .who, .culture: GapCard(item: g, text: body)
            case .bridge: BridgeChip(title: g.title, text: body) { onAction(card, .dismiss) }
            case .storyline: StorylineCard(title: g.title, states: g.states)
            case .ask:
                AskCard(term: g.term.isEmpty ? g.title : g.term, speakerName: speakerName, suggestions: g.suggestions,
                        onPick: { onAction(card, .place($0)) }, onNotNow: { onAction(card, .dismiss) })
            }
        }
    }
}
