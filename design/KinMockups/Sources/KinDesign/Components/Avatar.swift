import SwiftUI

/// Initial-based avatar. The initial is the person's name in their own script when they have one (林, பா).
public struct Avatar: View {
    let text: String
    let hue: Double
    let size: CGFloat
    public init(_ text: String, hue: Double, size: CGFloat = 44) { self.text = text; self.hue = hue; self.size = size }

    public var body: some View {
        Circle()
            .fill(LinearGradient(colors: [Color(hue: hue, saturation: 0.42, brightness: 0.82),
                                          Color(hue: hue, saturation: 0.55, brightness: 0.62)],
                                 startPoint: .topLeading, endPoint: .bottomTrailing))
            .overlay(Text(text).font(.system(size: size * 0.42, weight: .semibold)).foregroundStyle(.white))
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}

/// Demo cast colors, stable per person.
public enum Cast {
    public static let mei = (initial: "M", native: "美", hue: 0.96)
    public static let priya = (initial: "P", native: "P", hue: 0.08)
    public static let paatti = (initial: "K", native: "க", hue: 0.55)
    public static let arjun = (initial: "A", native: "A", hue: 0.62)
    public static let lin = (initial: "L", native: "林", hue: 0.36)
}
