import SwiftUI

// Design tokens.
// Neutrals follow Meta's light/dark system. App/Theme.swift keeps the older dark-only tokens for the screens that
// were not redesigned (sign-up, ended).

/// A color with a light and a dark value, resolved from the SwiftUI environment.
struct KinColor: ShapeStyle, Sendable {
    let light: Color
    let dark: Color
    init(_ light: UInt32, _ dark: UInt32) { self.light = Color(hex: light); self.dark = Color(hex: dark) }
    func resolve(in environment: EnvironmentValues) -> Color { environment.colorScheme == .dark ? dark : light }
}

enum K {
    static let bg = KinColor(0xFFFFFF, 0x18191A)
    static let grouped = KinColor(0xF0F2F5, 0x18191A)
    static let surface = KinColor(0xFFFFFF, 0x242526)
    static let raised = KinColor(0xF0F2F5, 0x3A3B3C)
    static let separator = KinColor(0xE4E6EB, 0x3E4042)
    static let text = KinColor(0x050505, 0xE4E6EB)
    static let text2 = KinColor(0x65676B, 0xB0B3B8)
    static let text3 = KinColor(0x8A8D91, 0x8A8D91)
    static let primary = KinColor(0x0064E0, 0x0064E0)
    static let link = KinColor(0x0064E0, 0x47A5FA)
    static let primarySoft = KinColor(0xE6F0FD, 0x1D3557)
    static let success = KinColor(0x31A24C, 0x31A24C)
    static let warning = KinColor(0xB07A00, 0xF7B928)  // darker in light mode for contrast on white
    static let error = KinColor(0xE41E3F, 0xF0284A)

    /// The call screen is always dark (it sits on video), so its overlay colors are fixed.
    enum Call {
        static let scrimBottom = Color.black.opacity(0.78)
        static let card = Color(hex: 0x242526).opacity(0.96)
        static let control = Color.white.opacity(0.16)
        static let text = Color.white
        static let text2 = Color.white.opacity(0.72)
        static let text3 = Color.white.opacity(0.52)
        static let mine = Color(hex: 0x0064E0)       // your bridge chip: the blue of your own messages
        static let highlight = Color(hex: 0x8CC4FF)  // a caption word that has a card
        static let on = Color(hex: 0x31A24C)
        static let end = Color(hex: 0xE41E3F)
    }
}

/// Type scale: every style is a Dynamic Type text style.
enum KinFont {
    static let largeTitle = Font.system(.largeTitle, weight: .bold)
    static let title = Font.system(.title, weight: .bold)
    static let title3 = Font.system(.title3, weight: .semibold)
    static let headline = Font.system(.headline, weight: .semibold)
    static let body = Font.system(.body)
    static let callout = Font.system(.callout)
    static let subhead = Font.system(.subheadline)
    static let subheadEmph = Font.system(.subheadline, weight: .semibold)
    static let footnote = Font.system(.footnote)
    static let footnoteEmph = Font.system(.footnote, weight: .semibold)
    static let caption = Font.system(.caption)
    static let captionEmph = Font.system(.caption, weight: .semibold)
    /// The live caption: the largest text on the call screen.
    static let captionLine = Font.system(.title2, weight: .semibold)
    static let captionOriginal = Font.system(.subheadline)
}

enum Space {
    static let xxs: CGFloat = 4, xs: CGFloat = 8, s: CGFloat = 12, m: CGFloat = 16, l: CGFloat = 20, xl: CGFloat = 24
    static let gutter: CGFloat = 16
}

enum Radius {
    static let card: CGFloat = 20, image: CGFloat = 14, field: CGFloat = 12, section: CGFloat = 16
}

enum KinMotion {
    /// Cards slide up from the caption area; with Reduce Motion they cross-fade.
    static let card = Animation.spring(response: 0.38, dampingFraction: 0.9)
    static let fade = Animation.easeOut(duration: 0.2)

    static func cardTransition(reduceMotion: Bool) -> AnyTransition {
        reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity)
    }
}
