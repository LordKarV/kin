import SwiftUI

// Card components for the call rail. Each takes plain values and closures so the design pass can restyle them
// without touching call logic.

/// "Who's that?": a person or thing from their world that I am missing (gap new) or have likely forgotten (reminder).
struct WhoCard: View {
    let title: String
    let native: String
    let line: String   // one line, with the source ("first mentioned Sep 14")
    let gap: String?   // new|reminder
    let onKnow: () -> Void

    var body: some View {
        CardShell {
            HStack(spacing: 6) {
                Text(title).font(Theme.cardTitleFont)
                if !native.isEmpty, native != title { Text(native).font(Theme.cardBodyFont).foregroundStyle(Theme.secondaryText) }
                Spacer(minLength: 4)
                if gap == "reminder" { Chip(text: "Reminder", color: Theme.warning) }
                else if gap == "new" { Chip(text: "New", color: Theme.accent) }
            }
            Text(line).font(Theme.cardBodyFont).foregroundStyle(Theme.secondaryText).lineLimit(3)
            CardButton(title: "I know", action: onKnow)
        }
    }
}

/// A private bridge: my own news the other person has not heard. Visible only to me.
struct BridgeChip: View {
    let title: String  // "You haven't told Mei"
    let text: String   // "you started bouldering"
    let onDismiss: () -> Void

    static let label = "Only you"
    var line: String { title.isEmpty ? text : "\(title): \(text)" }

    var body: some View {
        CardShell(tint: Theme.success.opacity(0.22)) {
            HStack {
                Chip(text: Self.label, color: Theme.success)
                Spacer()
                Button(action: onDismiss) { Image(systemName: "xmark").font(.caption.bold()) }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Dismiss")
            }
            Text(line).font(Theme.cardBodyFont).lineLimit(3)
        }
        .accessibilityElement(children: .contain)
        .accessibilityHint("Private suggestion, only you can see it")
    }
}

/// Where an ongoing thread stands, as a mini timeline. States I have not heard are highlighted.
struct StorylineCard: View {
    let title: String
    let states: [StoryState]

    var body: some View {
        CardShell {
            Text(title).font(Theme.cardTitleFont)
            HStack(alignment: .top, spacing: 0) {
                ForEach(Array(states.enumerated()), id: \.offset) { i, state in
                    if i > 0 { Rectangle().fill(Theme.field).frame(height: 2).padding(.top, 5).frame(maxWidth: 24) }
                    VStack(spacing: 3) {
                        Circle().fill(state.known ? Theme.field : Theme.accent).frame(width: 12, height: 12)
                        Text(state.label).font(Theme.cardMetaFont).multilineTextAlignment(.center)
                            .foregroundStyle(state.known ? Theme.secondaryText : .white)
                        Text(Self.month(state.at)).font(Theme.cardMetaFont).foregroundStyle(Theme.secondaryText)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    /// "2026-09-02" -> "Sep"; anything unparsable is shown as given.
    static func month(_ at: String) -> String {
        let parts = at.split(separator: "-")
        guard parts.count >= 2, let m = Int(parts[1]), (1...12).contains(m) else { return at }
        return DateFormatter().shortMonthSymbols[m - 1]
    }
}

/// "Who is X?": one tap places the person in the right world.
struct AskCard: View {
    let term: String
    let suggestions: [Suggestion]
    let onPick: (Suggestion) -> Void
    let onNotNow: () -> Void

    var body: some View {
        CardShell {
            Text("Who is \(term)?").font(Theme.cardTitleFont)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(suggestions, id: \.label) { s in CardButton(title: s.label, filled: true) { onPick(s) } }
                    CardButton(title: "Not now", action: onNotNow)
                }
            }
        }
    }
}

/// Cultural or pragmatic meaning, or a term card: what it says and what it means.
struct CultureCard: View {
    let title: String
    let meaning: String
    var note: String = ""

    var body: some View {
        CardShell {
            Text(title).font(Theme.cardTitleFont).lineLimit(2)
            Text(meaning).font(Theme.cardBodyFont).foregroundStyle(Theme.secondaryText).lineLimit(3)
            if !note.isEmpty { Text(note).font(Theme.cardMetaFont).foregroundStyle(Theme.secondaryText).lineLimit(2) }
        }
    }
}
