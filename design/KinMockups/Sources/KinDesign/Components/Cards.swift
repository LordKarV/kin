import SwiftUI

// Cards that explain THEIR world sit on the left, above the captions (where the words that triggered them are).
// Your private bridge chip sits on the right in your own blue, the same rule as a messaging thread.
// Every card is glanceable in under a second: one title, one line, one source.

private struct CallCardSurface: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 14).padding(.vertical, 11)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(K.Call.card, in: RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Radius.card, style: .continuous).stroke(Color.white.opacity(0.08), lineWidth: 1))
            .shadow(color: .black.opacity(0.3), radius: 16, y: 6)
    }
}

extension View { func callCard() -> some View { modifier(CallCardSurface()) } }

/// The small line above a card's title that says what kind of help this is.
struct Eyebrow: View {
    let symbol: String?; let text: String; let color: Color
    var body: some View {
        HStack(spacing: 4) {
            if let symbol { Image(systemName: symbol).font(.system(size: 10, weight: .bold)) }
            Text(text)
        }
        .font(KinFont.captionEmph).foregroundStyle(color)
    }
}

/// "Who's that?" (who/what) and culture terms (term/saying), straight from a `GlanceItem`.
public struct GapCard: View {
    let item: GlanceItem
    let viaTap: Bool                // true when this card answers the listener tapping a word (POST /explain)
    @Environment(\.kinStrings) private var str
    public init(_ item: GlanceItem, viaTap: Bool = false) { self.item = item; self.viaTap = viaTap }

    /// The engine sends "Mei's friend from the Fudan climbing wall, first mentioned Sep 14": the source clause gets its
    /// own quieter line so the identity reads first.
    var parts: (main: String, source: String?) {
        if let r = item.body.range(of: ", first mentioned ") {
            return (String(item.body[..<r.lowerBound]), "First mentioned " + item.body[r.upperBound...])
        }
        return (item.body, nil)
    }

    var isPerson: Bool { item.kind == "who" || item.kind == "what" }

    public var body: some View {
        HStack(alignment: .top, spacing: 12) {
            if isPerson {
                Avatar(item.native.isEmpty ? String(item.title.prefix(1)) : String(item.native.prefix(1)), hue: 0.36, size: 36)
            } else {
                RoundedRectangle(cornerRadius: 11, style: .continuous).fill(Color.white.opacity(0.1))
                    .overlay(Image(systemName: Self.symbol(for: item.category)).font(.system(size: 15, weight: .semibold)).foregroundStyle(K.Call.text2))
                    .frame(width: 36, height: 36).accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(item.title).font(KinFont.headline).foregroundStyle(K.Call.text)
                    if !item.native.isEmpty && item.native != item.title {
                        Text(item.native).font(KinFont.subhead).foregroundStyle(K.Call.text3)
                    }
                    Spacer(minLength: 8)
                    eyebrow
                }
                Text(parts.main).font(KinFont.subhead).foregroundStyle(K.Call.text2).lineLimit(2).fixedSize(horizontal: false, vertical: true)
                if let source = parts.source {
                    Text(source).font(KinFont.footnote).foregroundStyle(K.Call.text3)
                }
            }
        }
        .callCard()
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder var eyebrow: some View {
        if viaTap {
            Eyebrow(symbol: "hand.tap.fill", text: str.youAsked, color: K.Call.highlight)
        } else {
            pushEyebrow
        }
    }

    @ViewBuilder var pushEyebrow: some View {
        switch (item.kind, item.gap) {
        case ("who", "reminder"), ("what", "reminder"): Eyebrow(symbol: "clock.arrow.circlepath", text: str.reminder, color: K.Call.highlight)
        case ("who", _), ("what", _): Eyebrow(symbol: nil, text: str.newToYou, color: K.Call.text3)
        case ("saying", _): Eyebrow(symbol: nil, text: "Saying", color: K.Call.text3)
        default: Eyebrow(symbol: nil, text: item.category.isEmpty ? "Term" : item.category.capitalized, color: K.Call.text3)
        }
    }

    static func symbol(for category: String) -> String {
        switch category {
        case "food": return "fork.knife"
        case "festival": return "calendar"
        case "place": return "mappin.and.ellipse"
        case "address": return "person.2.fill"
        case "saying": return "quote.opening"
        default: return "text.book.closed.fill"
        }
    }
}

/// Cultural or pragmatic meaning (from `PragmaticsCard`, delivered with the transcript or as a late `enrich`).
public struct MeaningCard: View {
    let card: PragmaticsCard
    public init(_ card: PragmaticsCard) { self.card = card }
    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Eyebrow(symbol: "quote.opening", text: "What it means", color: K.Call.text3)
            if let literal = card.literal, !literal.isEmpty {
                Text("\u{201C}\(literal)\u{201D}").font(KinFont.subhead).foregroundStyle(K.Call.text2)
            }
            Text(card.meaning ?? "").font(KinFont.headline).foregroundStyle(K.Call.text).fixedSize(horizontal: false, vertical: true)
        }
        .callCard()
        .accessibilityElement(children: .combine)
    }
}

/// Where an ongoing thread stands. States you already know are quiet; the one you missed is marked.
public struct StorylineCard: View {
    let item: GlanceItem
    public init(_ item: GlanceItem) { self.item = item }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Eyebrow(symbol: "arrow.forward.circle.fill", text: "Catching up", color: K.Call.highlight)
                Text(item.title).font(KinFont.headline).foregroundStyle(K.Call.text)
            }
            HStack(alignment: .top, spacing: 0) {
                ForEach(Array(item.states.enumerated()), id: \.offset) { i, st in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 0) {
                            Circle().fill(st.known ? Color.white.opacity(0.45) : K.Call.highlight)
                                .frame(width: st.known ? 8 : 10, height: st.known ? 8 : 10)
                            if i < item.states.count - 1 {
                                Rectangle().fill(Color.white.opacity(0.22)).frame(height: 2)
                            }
                        }
                        .frame(height: 10)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(st.label.prefix(1).uppercased() + st.label.dropFirst())
                                .font(st.known ? KinFont.subhead : KinFont.subheadEmph)
                                .foregroundStyle(st.known ? K.Call.text2 : K.Call.text)
                            Text(Self.month(st.at) + (st.known ? "" : " · new to you"))
                                .font(KinFont.caption).foregroundStyle(st.known ? K.Call.text3 : K.Call.highlight)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
        .callCard()
        .accessibilityElement(children: .combine)
    }

    static func month(_ ymd: String) -> String {
        let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        let p = ymd.split(separator: "-")
        guard p.count == 3, let m = Int(p[1]), let d = Int(p[2]), (1...12).contains(m) else { return ymd }
        return "\(months[m - 1]) \(d)"
    }
}

/// "Who is Ravi mama?": a suggested relation is one tap. It waits for an answer instead of auto-dismissing,
/// but "Not now" is always there and the call never depends on it.
public struct AskCard: View {
    let item: GlanceItem
    let speakerName: String
    let viaTap: Bool
    @Environment(\.kinStrings) private var str
    public init(_ item: GlanceItem, speakerName: String, viaTap: Bool = false) { self.item = item; self.speakerName = speakerName; self.viaTap = viaTap }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Eyebrow(symbol: viaTap ? "hand.tap.fill" : "questionmark.circle.fill",
                        text: viaTap ? str.youAsked : "\(speakerName) mentioned", color: K.Call.highlight)
                Text("Who is \(item.term)?").font(KinFont.headline).foregroundStyle(K.Call.text)
                if viaTap {
                    Text("KIN doesn't know \(item.term) yet. Add them, and next time it can tell you.")
                        .font(KinFont.footnote).foregroundStyle(K.Call.text2).fixedSize(horizontal: false, vertical: true)
                }
            }
            // The two most likely relations from the language's kinship table: one tap adds the person.
            HStack(spacing: 8) {
                ForEach(Array(item.suggestions.prefix(2).enumerated()), id: \.offset) { i, s in chip(s.label, primary: i == 0) }
            }
            HStack {
                Button("Someone else") {}.buttonStyle(.plain).foregroundStyle(K.Call.highlight)
                Spacer()
                Button("Not now") {}.buttonStyle(.plain).foregroundStyle(K.Call.text2)
            }
            .font(KinFont.footnoteEmph).frame(height: 24)
        }
        .callCard()
    }

    private func chip(_ label: String, primary: Bool) -> some View {
        Button {} label: {
            Text(label).font(KinFont.footnoteEmph).lineLimit(1).minimumScaleFactor(0.85)
                .foregroundStyle(primary ? Color.black : Color.white)
                .padding(.horizontal, 10).frame(maxWidth: .infinity).frame(height: 38)
                .background(primary ? Color.white : Color.white.opacity(0.14), in: Capsule())
        }
        .buttonStyle(.plain)
    }
}

/// Your private nudge: something about YOU the other person has not heard, relevant to what they just said.
/// Right-aligned in your blue like your own message bubble, and labelled as visible only to you.
public struct BridgeChip: View {
    let item: GlanceItem
    public init(_ item: GlanceItem) { self.item = item }

    @Environment(\.kinStrings) private var str

    public var body: some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Image(systemName: "lock.fill").font(.system(size: 9, weight: .bold))
                    Text(item.title)
                }
                .font(KinFont.footnoteEmph).foregroundStyle(Color.white.opacity(0.82))
                Text(item.body.prefix(1).uppercased() + item.body.dropFirst())
                    .font(KinFont.headline).foregroundStyle(.white).fixedSize(horizontal: false, vertical: true)
            }
            Button {} label: {
                Image(systemName: "xmark").font(.system(size: 10, weight: .bold)).foregroundStyle(Color.white.opacity(0.85))
                    .frame(width: 26, height: 26).background(Color.white.opacity(0.18), in: Circle())
                    .frame(width: 44, height: 44)
            }
            .buttonStyle(.plain).accessibilityLabel("Dismiss")
        }
        .padding(.leading, 14).padding(.trailing, 2).padding(.top, 12).padding(.bottom, 6)
        .background(K.Call.mine, in: RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
        .overlay(alignment: .topTrailing) {
            Text(str.onlyYou).font(.system(size: 10, weight: .bold)).foregroundStyle(K.Call.mine)
                .padding(.horizontal, 7).frame(height: 18).background(Color.white, in: Capsule())
                .offset(x: -12, y: -10)
        }
        .shadow(color: .black.opacity(0.3), radius: 16, y: 6)
        .frame(maxWidth: 300, alignment: .trailing)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Only you can see this. \(item.title): \(item.body)")
    }
}

/// Wraps chips onto multiple lines.
public struct FlowLayout: Layout {
    var spacing: CGFloat
    public init(spacing: CGFloat = 8) { self.spacing = spacing }
    public func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 320
        var x: CGFloat = 0, y: CGFloat = 0, row: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > 0 && x + s.width > width { y += row + spacing; x = 0; row = 0 }
            x += s.width + spacing; row = max(row, s.height)
        }
        return CGSize(width: width, height: y + row)
    }
    public func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, row: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > bounds.minX && x + s.width > bounds.maxX { y += row + spacing; x = bounds.minX; row = 0 }
            v.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(s))
            x += s.width + spacing; row = max(row, s.height)
        }
    }
}
