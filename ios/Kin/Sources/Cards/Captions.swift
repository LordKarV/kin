import SwiftUI

/// Live captions (design-notes layout rules 4 to 6). The big line is the latest line I can read and changes only when
/// a final lands; the other person's live words show small underneath with a typing indicator. The word behind the
/// card on screen is tinted and dotted-underlined; every other name or term is quietly tappable (a faint dotted
/// underline) and opens `kin-explain:` links that the call screen turns into a tap-to-explain request.
struct LiveCaptions: View {
    let speakerName: String
    let route: (from: String, to: String)?  // languages of the current line; nil when it needed no translation
    let crossLanguage: Bool                 // someone on the call speaks another language: offer translated voice
    let previous: Caption?
    let current: Caption?
    let partial: Caption?
    let tappable: [String]
    let tappableOriginal: [String]  // names in the speaker's own words (grounded span sources)
    let highlights: [String]
    let hint: String?
    let voiceOn: Bool
    let onToggleVoice: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                if !speakerName.isEmpty { Text(speakerName).font(KinFont.footnoteEmph).foregroundStyle(K.Call.text2) }
                if let route { RouteLabel(from: route.from, to: route.to).padding(.leading, 2) }
                Spacer()
                if crossLanguage { voiceToggle }
            }
            if let previous {
                Text(previous.text).font(KinFont.callout).foregroundStyle(K.Call.text3).lineLimit(1)
            }
            if let current {
                if let original = current.original {
                    Text(Self.styled(original, tappable: tappableOriginal, highlights: []))
                        .font(KinFont.captionOriginal).tint(K.Call.text2).foregroundStyle(K.Call.text2).lineLimit(1)
                }
                Text(Self.styled(current.text, tappable: tappable, highlights: highlights))
                    .font(KinFont.captionLine).foregroundStyle(K.Call.text)
                    .tint(K.Call.text)  // links keep the caption color; the attributes below carry the affordance
                    .lineSpacing(2).lineLimit(3).fixedSize(horizontal: false, vertical: true)
            }
            if let partial {
                HStack(spacing: 6) {
                    TypingDots()
                    Text(partial.text).font(KinFont.callout).foregroundStyle(K.Call.text2).lineLimit(1)
                        .truncationMode(.head)  // a growing line keeps its newest words
                }
                .padding(.top, 2)
            }
            if let hint { Text(hint).font(KinFont.footnote).foregroundStyle(K.Call.text3) }
        }
        .accessibilityElement(children: .contain)
    }

    private var voiceToggle: some View {
        Button(action: onToggleVoice) {
            HStack(spacing: 5) {
                Image(systemName: voiceOn ? "speaker.wave.2.fill" : "speaker.slash.fill")
                Text(voiceOn ? "Voice on" : "Voice off")
            }
            .font(KinFont.captionEmph)
            .foregroundStyle(voiceOn ? .white : K.Call.text2)
            .padding(.horizontal, 10).frame(height: 28)
            .background(voiceOn ? K.Call.mine : Color.white.opacity(0.14), in: Capsule())
            .frame(minHeight: 44)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(voiceOn ? "Translated voice on. Tap to turn off." : "Translated voice off. Tap to hear translations spoken.")
    }

    /// Tappable terms become links; the card's trigger word is also tinted. Longer terms are applied first and a
    /// range already linked is never relinked, so "Ravi mama" is one tap, not two.
    static func styled(_ text: String, tappable: [String], highlights: [String]) -> AttributedString {
        var a = AttributedString(text)
        var taken: [Range<AttributedString.Index>] = []
        let all = (highlights + tappable).sorted { $0.count > $1.count }
        for term in all {
            for sr in termRanges(of: term, in: text) {
                guard let r = Range(sr, in: a), !taken.contains(where: { $0.overlaps(r) }), let url = ExplainLink.url(term) else { continue }
                taken.append(r)
                let hot = highlights.contains(term)
                a[r].link = url
                a[r].foregroundColor = hot ? K.Call.highlight : K.Call.text
                a[r].underlineStyle = Text.LineStyle(pattern: .dot, color: hot ? K.Call.highlight.opacity(0.8) : Color.white.opacity(0.35))
            }
        }
        return a
    }
}

/// "Source -> Target": the languages of the current translation.
struct RouteLabel: View {
    let from: String
    let to: String

    var body: some View {
        HStack(spacing: 4) {
            Text(from)
            Image(systemName: "arrow.right").font(.caption2.weight(.bold))
            Text(to)
        }
        .font(KinFont.footnote).foregroundStyle(K.Call.text3)
        .accessibilityElement(children: .ignore).accessibilityLabel("Translating \(from) to \(to)")
    }
}

struct TypingDots: View {
    var body: some View {
        HStack(spacing: 3) { ForEach(0..<3) { i in Circle().fill(Color.white.opacity(0.4 + Double(i) * 0.2)).frame(width: 5, height: 5) } }
            .accessibilityLabel("Speaking")
    }
}
