import SwiftUI

// Type and size tokens for the call screen. Colors and radii live in App/Theme.swift (the `Theme` enum); these
// extend it so the design pass restyles one place. All fonts are text styles, so Dynamic Type scales them.
extension Theme {
    static let captionFont = Font.title2.weight(.semibold)
    static let captionSpeakerFont = Font.footnote.weight(.semibold)
    static let cardTitleFont = Font.headline
    static let cardBodyFont = Font.subheadline
    static let cardMetaFont = Font.caption
    static let chipFont = Font.caption2.weight(.bold)
    static let cardWidth: CGFloat = 220
    static let controlSize: CGFloat = 52
    static let secondaryText = Color.white.opacity(0.7)
}

/// Small rounded label: "New", "Reminder", "Only you".
struct Chip: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(Theme.chipFont)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .foregroundStyle(color)
            .background(color.opacity(0.18), in: Capsule())
    }
}

/// Card container on the surface color with the standard radius.
struct CardShell<Content: View>: View {
    var tint: Color = Theme.surface
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) { content }
            .padding(12)
            .frame(width: Theme.cardWidth, alignment: .leading)
            .background(tint, in: RoundedRectangle(cornerRadius: Theme.radius))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius).stroke(Color.white.opacity(0.08)))
    }
}

/// Small text button used inside cards.
struct CardButton: View {
    let title: String
    var filled = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.footnote.weight(.semibold))
                .padding(.horizontal, 12).padding(.vertical, 6)
                .foregroundStyle(.white)
                .background(filled ? AnyShapeStyle(Theme.primaryGradient) : AnyShapeStyle(Theme.field), in: Capsule())
        }
        .buttonStyle(.plain)
    }
}
