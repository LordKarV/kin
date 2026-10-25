import SwiftUI

// MARK: - Color

/// A color token with a light and a dark value, resolved from the SwiftUI environment (works in previews and renders).
public struct KinColor: ShapeStyle, Sendable {
    public let light: Color
    public let dark: Color
    public init(_ light: UInt32, _ dark: UInt32) { self.light = Color(hex: light); self.dark = Color(hex: dark) }
    public init(light: Color, dark: Color) { self.light = light; self.dark = dark }
    public func resolve(in environment: EnvironmentValues) -> Color { environment.colorScheme == .dark ? dark : light }
}

public extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255, opacity: alpha)
    }
}

/// Design tokens. Neutrals follow Meta's own light/dark system (Facebook, Messenger) so KIN sits naturally next to
/// Meta apps; KIN's identity comes from restraint, type and layout rather than from a new palette.
public enum K {
    // Surfaces
    public static let bg = KinColor(0xFFFFFF, 0x18191A)
    public static let grouped = KinColor(0xF0F2F5, 0x18191A)
    public static let surface = KinColor(0xFFFFFF, 0x242526)
    public static let raised = KinColor(0xF0F2F5, 0x3A3B3C)
    public static let separator = KinColor(0xE4E6EB, 0x3E4042)
    // Text
    public static let text = KinColor(0x050505, 0xE4E6EB)
    public static let text2 = KinColor(0x65676B, 0xB0B3B8)
    public static let text3 = KinColor(0x8A8D91, 0x8A8D91)
    // Brand and state
    public static let primary = KinColor(0x0064E0, 0x0064E0)       // fills (buttons, your bubble)
    public static let link = KinColor(0x0064E0, 0x47A5FA)          // tinted text and icons
    public static let primarySoft = KinColor(0xE6F0FD, 0x1D3557)   // selected chip, info background
    public static let success = KinColor(0x31A24C, 0x31A24C)
    public static let warning = KinColor(0xB07A00, 0xF7B928)       // darker in light mode for contrast on white
    public static let error = KinColor(0xE41E3F, 0xF0284A)

    /// The call screen is always dark (video), so its overlay colors are fixed.
    public enum Call {
        public static let scrimTop = Color.black.opacity(0.0)
        public static let scrimBottom = Color.black.opacity(0.78)
        public static let card = Color(hex: 0x242526, alpha: 0.96)
        public static let control = Color.white.opacity(0.16)
        public static let controlOn = Color.white
        public static let text = Color.white
        public static let text2 = Color.white.opacity(0.72)
        public static let text3 = Color.white.opacity(0.52)
        public static let mine = Color(hex: 0x0064E0)               // your bridge chip: same blue as your own messages
        public static let highlight = Color(hex: 0x8CC4FF)          // a word in a caption that has a card
        public static let end = Color(hex: 0xE41E3F)
    }
}

// MARK: - Type

/// Type scale. On iOS every style is a Dynamic Type text style (scales with the user's setting); the fixed sizes are
/// the iOS default sizes, used only when rendering screenshots on macOS where text styles are smaller.
public enum KinFont {
    static func s(_ style: Font.TextStyle, _ size: CGFloat, _ weight: Font.Weight) -> Font {
        #if os(iOS)
        return .system(style, design: .default, weight: weight)
        #else
        return .system(size: size, weight: weight)
        #endif
    }
    public static let largeTitle = s(.largeTitle, 34, .bold)
    public static let title = s(.title, 28, .bold)
    public static let title2 = s(.title2, 22, .bold)
    public static let title3 = s(.title3, 20, .semibold)
    public static let headline = s(.headline, 17, .semibold)
    public static let body = s(.body, 17, .regular)
    public static let callout = s(.callout, 16, .regular)
    public static let calloutEmph = s(.callout, 16, .semibold)
    public static let subhead = s(.subheadline, 15, .regular)
    public static let subheadEmph = s(.subheadline, 15, .semibold)
    public static let footnote = s(.footnote, 13, .regular)
    public static let footnoteEmph = s(.footnote, 13, .semibold)
    public static let caption = s(.caption, 12, .regular)
    public static let captionEmph = s(.caption, 12, .semibold)
    /// Live captions: the translated line is the largest text on the call screen.
    public static let captionLine = s(.title2, 22, .semibold)
    public static let captionOriginal = s(.subheadline, 15, .regular)
}

// MARK: - Spacing, radius, motion

public enum Space {
    public static let xxs: CGFloat = 4, xs: CGFloat = 8, s: CGFloat = 12, m: CGFloat = 16, l: CGFloat = 20,
                      xl: CGFloat = 24, xxl: CGFloat = 32
    public static let gutter: CGFloat = 16   // screen edge
}

public enum Radius {
    public static let card: CGFloat = 20, image: CGFloat = 14, field: CGFloat = 12, chip: CGFloat = 999
}

public enum KinMotion {
    /// Cards slide up from the caption area. With Reduce Motion they cross-fade instead.
    public static let card = Animation.spring(response: 0.38, dampingFraction: 0.9)
    public static let fade = Animation.easeOut(duration: 0.2)
    /// How long a card stays when nobody touches it. A touch pauses the timer; leaving restarts it at 2 s.
    public static let dwellSeconds: Double = 7
    public static let bridgeDwellSeconds: Double = 10
    /// At most one bridge every 90 s per listener (matches the engine's rate limit).
    public static let bridgeMinGapSeconds: Double = 90
}
