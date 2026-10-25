import SwiftUI

/// One caption line, built from a `Transcript` (final) or a `Partial` (still speaking).
public struct Caption: Identifiable, Equatable {
    public let id: Int
    public let original: String
    public let translation: String?   // nil when both people share a language
    public init(id: Int, original: String, translation: String?) { self.id = id; self.original = original; self.translation = translation }
    public init(_ t: Transcript) { self.init(id: t.utteranceId, original: t.srcText, translation: t.translation) }
    /// The line the listener reads: the translation, or the original when no translation is needed.
    public var readable: String { translation ?? original }
}

/// Live captions, the default way translation is shown. The big line is the latest line the listener can read; it
/// does not jitter while the other person is still talking. The live partial (in the speaker's language) shows small
/// underneath so you can see they are mid-sentence. Words that have a card are tinted and dotted-underlined, so it is
/// always clear why a card appeared.
public struct LiveCaptions: View {
    let speakerName: String
    let route: (from: String, to: String)?   // language names in the listener's language; nil for same-language calls
    let previous: Caption?
    let current: Caption?
    let partial: String?
    let highlights: [String]
    let voiceOn: Bool
    let onToggleVoice: () -> Void
    @Environment(\.kinStrings) private var str

    public init(speakerName: String, route: (from: String, to: String)?, previous: Caption? = nil, current: Caption?, partial: String? = nil,
                highlights: [String] = [], voiceOn: Bool = false, onToggleVoice: @escaping () -> Void = {}) {
        self.speakerName = speakerName; self.route = route; self.previous = previous; self.current = current
        self.partial = partial; self.highlights = highlights; self.voiceOn = voiceOn; self.onToggleVoice = onToggleVoice
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Text(speakerName).font(KinFont.footnoteEmph).foregroundStyle(K.Call.text2)
                if let route { RouteLabel(route).padding(.leading, 2) }
                Spacer()
                if route != nil { voiceToggle }
            }
            if let previous {
                Text(previous.readable).font(KinFont.callout).foregroundStyle(K.Call.text3).lineLimit(1)
            }
            if let current {
                if current.translation != nil {
                    Text(current.original).font(KinFont.captionOriginal).foregroundStyle(K.Call.text2).lineLimit(1)
                }
                Text(Self.highlighted(current.readable, highlights))
                    .font(KinFont.captionLine).foregroundStyle(K.Call.text)
                    .lineSpacing(2).lineLimit(3).fixedSize(horizontal: false, vertical: true)
            }
            if let partial {
                HStack(spacing: 6) {
                    TypingDots()
                    Text(partial).font(KinFont.callout).foregroundStyle(K.Call.text2).lineLimit(1)
                }
                .padding(.top, 2)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var voiceToggle: some View {
        Button(action: onToggleVoice) {
            HStack(spacing: 5) {
                Image(systemName: voiceOn ? "speaker.wave.2.fill" : "speaker.slash.fill")
                Text(voiceOn ? str.voiceOn : str.voiceOff)
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

    static func highlighted(_ text: String, _ words: [String]) -> AttributedString {
        var a = AttributedString(text)
        for w in words where !w.isEmpty {
            var search = a.startIndex..<a.endIndex
            while let r = a[search].range(of: w) {
                a[r].foregroundColor = K.Call.highlight
                a[r].underlineStyle = Text.LineStyle(pattern: .dot, color: K.Call.highlight.opacity(0.8))
                search = r.upperBound..<a.endIndex
            }
        }
        return a
    }
}

/// "Mandarin [arrow] English": the languages of the current translation, in the listener's language.
public struct RouteLabel: View {
    let route: (from: String, to: String)
    public init(_ route: (from: String, to: String)) { self.route = route }
    public var body: some View {
        HStack(spacing: 4) {
            Text(route.from)
            Image(systemName: "arrow.right").font(.system(size: 9, weight: .bold))
            Text(route.to)
        }
        .font(KinFont.footnote).foregroundStyle(K.Call.text3)
        .accessibilityElement(children: .ignore).accessibilityLabel("Translating \(route.from) to \(route.to)")
    }
}

struct TypingDots: View {
    var body: some View {
        HStack(spacing: 3) { ForEach(0..<3) { i in Circle().fill(Color.white.opacity(0.4 + Double(i) * 0.2)).frame(width: 5, height: 5) } }
            .accessibilityLabel("Speaking")
    }
}
