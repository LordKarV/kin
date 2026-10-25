import SwiftUI

/// What the user did to a card. The call screen turns these into REST calls and reducer updates.
enum CardAction: Equatable {
    case know
    case dismiss
    case place(Suggestion)
    case touch(Bool)
}

/// The rail of up to `WorldState.railCap` cards, newest first, scrolling sideways at the screen edge.
struct CardRail: View {
    let cards: [RailCard]
    let onAction: (RailCard, CardAction) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 10) {
                ForEach(cards) { card in
                    view(for: card)
                        .onLongPressGesture(minimumDuration: 0.2, maximumDistance: 20, perform: {}) { pressing in
                            onAction(card, .touch(pressing))
                        }
                        .transition(.move(edge: .trailing).combined(with: .opacity))
                }
            }
            .padding(.horizontal, 16)
        }
        .animation(.easeOut(duration: 0.25), value: cards.map(\.key))
    }

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

    @ViewBuilder private func view(for card: RailCard) -> some View {
        switch card.content {
        case .culture(let p):
            CultureCard(title: p.source ?? p.literal ?? "Meaning", meaning: p.meaning ?? "", note: p.whyItMatters ?? "")
        case .glance(let g, let body):
            switch Self.style(for: card) {
            case .who:
                WhoCard(title: g.title, native: g.native, line: body, gap: g.gap) { onAction(card, .know) }
            case .bridge:
                BridgeChip(title: g.title, text: body) { onAction(card, .dismiss) }
            case .storyline:
                StorylineCard(title: g.title, states: g.states)
            case .ask:
                AskCard(term: g.term.isEmpty ? g.title : g.term, suggestions: g.suggestions,
                        onPick: { onAction(card, .place($0)) }, onNotNow: { onAction(card, .dismiss) })
            case .culture:
                CultureCard(title: g.native.isEmpty ? g.title : "\(g.title) (\(g.native))", meaning: body)
            }
        }
    }
}
