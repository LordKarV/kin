import SwiftUI

// Call cards, ported from design/KinMockups/Sources/KinDesign/Components/Cards.swift. Cards about THEIR world sit on
// the left above the captions; your private bridge chip sits on the right in your blue (design-notes layout rule 1).
// Each takes the wire types plus closures, so the call logic stays in CallView.

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
    let symbol: String?
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 4) {
            if let symbol { Image(systemName: symbol).font(.caption2.weight(.bold)) }
            Text(text)
        }
        .font(KinFont.captionEmph).foregroundStyle(color)
    }
}

/// Initial avatar. The initial is in the person's own script when there is one (林, க), so cross-script names show.
struct Avatar: View {
    let text: String
    let size: CGFloat
    var hue: Double? = nil

    /// A stable hue per name, so the same person keeps the same color everywhere.
    static func hue(for key: String) -> Double {
        Double(key.unicodeScalars.reduce(UInt32(7)) { ($0 &* 31) &+ $1.value } % 360) / 360
    }

    var body: some View {
        let h = hue ?? Self.hue(for: text)
        Circle()
            .fill(LinearGradient(colors: [Color(hue: h, saturation: 0.42, brightness: 0.82),
                                          Color(hue: h, saturation: 0.55, brightness: 0.62)],
                                 startPoint: .topLeading, endPoint: .bottomTrailing))
            .overlay(Text(text).font(.system(size: size * 0.42, weight: .semibold)).foregroundStyle(.white))
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }

    static func initial(name: String, native: String = "") -> String {
        String((native.isEmpty ? name : native).prefix(1)).uppercased()
    }
}

/// "Who's that?" (who/what) and culture terms (term/saying, and kinds this build does not know yet).
struct GapCard: View {
    let item: GlanceItem
    let text: String  // the body; glance_update can swap it

    /// The engine sends "..., first mentioned Sep 14": the source clause gets its own quieter line.
    static func parts(_ body: String) -> (main: String, source: String?) {
        if let r = body.range(of: ", first mentioned ") {
            return (String(body[..<r.lowerBound]), "First mentioned " + body[r.upperBound...])
        }
        return (body, nil)
    }

    var isPerson: Bool { item.kind == "who" || item.kind == "what" }

    var body: some View {
        let parts = Self.parts(text)
        HStack(alignment: .top, spacing: 12) {
            if isPerson {
                Avatar(text: Avatar.initial(name: item.title, native: item.native), size: 36,
                       hue: Avatar.hue(for: item.nodeId ?? item.title))
            } else {
                RoundedRectangle(cornerRadius: 11, style: .continuous).fill(Color.white.opacity(0.1))
                    .overlay(Image(systemName: Self.symbol(for: item.category)).font(.subheadline.weight(.semibold))
                        .foregroundStyle(K.Call.text2))
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
                Text(parts.main).font(KinFont.subhead).foregroundStyle(K.Call.text2)
                    .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                if let source = parts.source { Text(source).font(KinFont.footnote).foregroundStyle(K.Call.text3) }
            }
        }
        .callCard()
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder var eyebrow: some View {
        switch (isPerson, item.gap, item.kind) {
        case (true, "reminder", _): Eyebrow(symbol: "clock.arrow.circlepath", text: "Reminder", color: K.Call.highlight)
        case (true, nil, _): Eyebrow(symbol: "hand.tap", text: "You asked", color: K.Call.text3)  // tap-to-explain
        case (true, _, _): Eyebrow(symbol: nil, text: "New to you", color: K.Call.text3)
        case (false, _, "saying"): Eyebrow(symbol: nil, text: "Saying", color: K.Call.text3)
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

/// Cultural or pragmatic meaning: the literal line in quotes, then what it means.
struct MeaningCard: View {
    let card: PragmaticsCard

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Eyebrow(symbol: "quote.opening", text: "What it means", color: K.Call.text3)
            if let literal = card.literal ?? card.source, !literal.isEmpty {
                Text("\u{201C}\(literal)\u{201D}").font(KinFont.subhead).foregroundStyle(K.Call.text2)
            }
            Text(card.meaning ?? "").font(KinFont.headline).foregroundStyle(K.Call.text)
                .fixedSize(horizontal: false, vertical: true)
            if let why = card.whyItMatters, !why.isEmpty {
                Text(why).font(KinFont.footnote).foregroundStyle(K.Call.text3).lineLimit(2)
            }
        }
        .callCard()
        .accessibilityElement(children: .combine)
    }
}

/// Where an ongoing thread stands. States you already knew are quiet; the one you missed is marked.
struct StorylineCard: View {
    let title: String
    let states: [StoryState]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Eyebrow(symbol: "arrow.forward.circle.fill", text: "Catching up", color: K.Call.highlight)
                Text(title).font(KinFont.headline).foregroundStyle(K.Call.text)
            }
            HStack(alignment: .top, spacing: 0) {
                ForEach(Array(states.enumerated()), id: \.offset) { i, st in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 0) {
                            Circle().fill(st.known ? Color.white.opacity(0.45) : K.Call.highlight)
                                .frame(width: st.known ? 8 : 10, height: st.known ? 8 : 10)
                            if i < states.count - 1 { Rectangle().fill(Color.white.opacity(0.22)).frame(height: 2) }
                        }
                        .frame(height: 10)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(st.label.prefix(1).uppercased() + st.label.dropFirst())
                                .font(st.known ? KinFont.subhead : KinFont.subheadEmph)
                                .foregroundStyle(st.known ? K.Call.text2 : K.Call.text)
                            Text(Self.day(st.at) + (st.known ? "" : " \u{00B7} new to you"))
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

    /// "2026-10-10" -> "Oct 10"; anything unparsable is shown as given.
    static func day(_ ymd: String) -> String {
        let p = ymd.split(separator: "-")
        guard p.count == 3, let m = Int(p[1]), let d = Int(p[2]), (1...12).contains(m) else { return ymd }
        return "\(Self.months[m - 1]) \(d)"
    }

    static let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
}

/// "Who is Ravi mama?": the two most likely relations are one tap each; "Not now" is always there.
/// ponytail: the mockup's "Someone else" picker is skipped; add it with GET /api/world/relations when asked for.
struct AskCard: View {
    let term: String
    let speakerName: String
    let suggestions: [Suggestion]
    let onPick: (Suggestion) -> Void
    let onNotNow: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Eyebrow(symbol: "questionmark.circle.fill",
                        text: speakerName.isEmpty ? "You asked" : "\(speakerName) mentioned", color: K.Call.highlight)
                Text("Who is \(term)?").font(KinFont.headline).foregroundStyle(K.Call.text)
            }
            if !suggestions.isEmpty {
                HStack(spacing: 8) {
                    ForEach(Array(suggestions.prefix(2).enumerated()), id: \.offset) { i, s in
                        Button { onPick(s) } label: {
                            Text(s.label).font(KinFont.footnoteEmph).lineLimit(1).minimumScaleFactor(0.85)
                                .foregroundStyle(i == 0 ? Color.black : Color.white)
                                .padding(.horizontal, 10).frame(maxWidth: .infinity).frame(height: 38)
                                .background(i == 0 ? Color.white : Color.white.opacity(0.14), in: Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            HStack {
                Spacer()
                Button("Not now", action: onNotNow).buttonStyle(.plain).foregroundStyle(K.Call.text2)
                    .contentShape(Rectangle().inset(by: -10))  // 44 pt target without growing the row
            }
            .font(KinFont.footnoteEmph).frame(height: 24)
        }
        .callCard()
    }
}

/// Your private nudge: your own news the other person has not heard. Right-aligned in your blue, labelled private.
struct BridgeChip: View {
    let title: String  // "You haven't told Mei"
    let text: String   // "started bouldering"
    let onDismiss: () -> Void

    static let label = "Only you see this"
    /// The fact reads after the title, so its first letter is capitalized on its own line.
    var line: String { text.prefix(1).uppercased() + text.dropFirst() }
    var accessibilityText: String { "Private to you. \(title.isEmpty ? "" : "\(title): ")\(text)" }

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                if !title.isEmpty {
                    HStack(spacing: 5) {
                        Image(systemName: "lock.fill").font(.caption2.weight(.bold))
                        Text(title)
                    }
                    .font(KinFont.footnoteEmph).foregroundStyle(Color.white.opacity(0.82))
                }
                Text(line).font(KinFont.headline).foregroundStyle(.white).fixedSize(horizontal: false, vertical: true)
            }
            Button(action: onDismiss) {
                Image(systemName: "xmark").font(.caption2.weight(.bold)).foregroundStyle(Color.white.opacity(0.85))
                    .frame(width: 26, height: 26).background(Color.white.opacity(0.18), in: Circle())
                    .frame(width: 44, height: 44)
            }
            .buttonStyle(.plain).accessibilityLabel("Dismiss")
        }
        .padding(.leading, 14).padding(.trailing, 2).padding(.vertical, 6)
        .background(K.Call.mine, in: RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
        .overlay(alignment: .topTrailing) {
            Text(Self.label).font(.caption2.weight(.bold)).foregroundStyle(K.Call.mine)
                .padding(.horizontal, 7).frame(height: 18).background(Color.white, in: Capsule())
                .offset(x: -12, y: -9)
        }
        .shadow(color: .black.opacity(0.3), radius: 16, y: 6)
        .frame(maxWidth: 300, alignment: .trailing)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
    }
}
