import SwiftUI

// Building blocks for the non-call screens. Light by
// default, dark through the KinColor tokens.

/// A titled rounded group, like an inset grouped list section.
struct KinSection<Content: View>: View {
    var title: String?
    var footer: String?
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title { Text(title).font(KinFont.subheadEmph).foregroundStyle(K.text2).padding(.horizontal, 4) }
            VStack(spacing: 0) { content }
                .background(K.surface, in: RoundedRectangle(cornerRadius: Radius.section, style: .continuous))
            if let footer {
                Text(footer).font(KinFont.footnote).foregroundStyle(K.text3).padding(.horizontal, 4)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, Space.gutter)
    }
}

struct Hairline: View {
    var inset: CGFloat = 16
    var body: some View { Rectangle().fill(K.separator).frame(height: 0.5).padding(.leading, inset) }
}

/// Small rounded label: a language, a status ("In progress").
struct Tag: View {
    let text: String
    var symbol: String?
    var tint: KinColor = K.text2
    var fill: KinColor = K.raised

    var body: some View {
        HStack(spacing: 4) {
            if let symbol { Image(systemName: symbol).font(.caption2.weight(.bold)) }
            Text(text)
        }
        .font(KinFont.captionEmph).foregroundStyle(tint)
        .padding(.horizontal, 8).frame(height: 22).background(fill, in: Capsule())
    }
}

struct CircleIcon: View {
    let symbol: String
    var tint: KinColor = K.text
    var fill: KinColor = K.surface
    var size: CGFloat = 36

    var body: some View {
        Image(systemName: symbol).font(.system(size: size * 0.44, weight: .semibold)).foregroundStyle(tint)
            .frame(width: size, height: size).background(fill, in: Circle())
            .frame(minWidth: 44, minHeight: 44)
    }
}

/// Filled (primary) or outlined capsule button, 52 pt tall.
struct CapsuleButton: View {
    let title: String
    var symbol: String?
    var primary = true
    var busy = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if busy { ProgressView().tint(primary ? .white : nil) } else if let symbol { Image(systemName: symbol) }
                Text(title)
            }
            .font(KinFont.headline).foregroundStyle(primary ? AnyShapeStyle(Color.white) : AnyShapeStyle(K.text))
            .frame(maxWidth: .infinity).frame(height: 52)
            .background(primary ? AnyShapeStyle(K.primary) : AnyShapeStyle(K.surface), in: Capsule())
            .overlay(Capsule().stroke(primary ? AnyShapeStyle(Color.clear) : AnyShapeStyle(K.separator), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(busy)
    }
}

/// "Where did this come from": every remembered item says who said it.
struct SourceLine: View {
    let text: String

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "text.bubble").font(.caption2.weight(.semibold))
            Text(text)
        }
        .font(KinFont.footnote).foregroundStyle(K.text3)
    }
}

/// A load failure inside a screen, with one retry.
struct LoadError: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 8) {
            Text(message).font(KinFont.subhead).foregroundStyle(K.error).multilineTextAlignment(.center)
            Button("Try again", action: retry).font(KinFont.subheadEmph).foregroundStyle(K.link)
        }
        .frame(maxWidth: .infinity).padding(Space.m)
    }
}

/// Language name in my own language (a code like "zh" -> its localized name).
func languageName(_ code: String) -> String { Locale.current.localizedString(forLanguageCode: code) ?? code }
