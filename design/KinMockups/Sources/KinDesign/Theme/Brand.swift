import SwiftUI

// KIN brand: two people's worlds overlap, and the overlap (the common ground) glows warm.
// One mark, used for the app icon, the launch screen and the launch film. Everything is drawn in code so it stays
// sharp at any size and the colors match the app tokens exactly.

public enum BrandColor {
    public static let blueTop = Color(hex: 0x2A8BFF)
    public static let blueBottom = Color(hex: 0x0058D6)
    public static let warm = Color(hex: 0xFFC94D)          // the common ground
    public static let warmDeep = Color(hex: 0xFFA826)
    public static var background: LinearGradient {
        LinearGradient(colors: [blueTop, blueBottom], startPoint: .topLeading, endPoint: .bottomTrailing)
    }
}

/// The mark on its own (transparent background). `style` picks colors for blue, dark or tinted backgrounds.
public struct KinMark: View {
    public enum Style { case onBlue, onDark, tinted, onLight }
    let size: CGFloat
    let style: Style
    public init(size: CGFloat, style: Style = .onBlue) { self.size = size; self.style = style }

    public var body: some View {
        let d = size * 0.54                         // circle diameter (about 11 percent margin each side)
        let a = CGPoint(x: size * 0.38, y: size * 0.53), b = CGPoint(x: size * 0.62, y: size * 0.47)
        ZStack {
            circle(d, at: a, fill: worldFill)
            circle(d, at: b, fill: worldFill)
            // the overlap, clipped from one circle by the other
            Circle().fill(groundFill).frame(width: d, height: d).position(a)
                .mask(Circle().frame(width: d, height: d).position(b))
        }
        .frame(width: size, height: size)
        .accessibilityLabel("KIN")
    }

    private func circle(_ d: CGFloat, at p: CGPoint, fill: AnyShapeStyle) -> some View {
        Circle().fill(fill).frame(width: d, height: d).position(p)
    }

    private var worldFill: AnyShapeStyle {
        switch style {
        case .onBlue: return AnyShapeStyle(Color.white.opacity(0.30))
        case .onDark: return AnyShapeStyle(LinearGradient(colors: [BrandColor.blueTop, BrandColor.blueBottom], startPoint: .topLeading, endPoint: .bottomTrailing).opacity(0.85))
        case .tinted: return AnyShapeStyle(Color.white.opacity(0.42))
        case .onLight: return AnyShapeStyle(LinearGradient(colors: [BrandColor.blueTop, BrandColor.blueBottom], startPoint: .topLeading, endPoint: .bottomTrailing).opacity(0.9))
        }
    }

    private var groundFill: AnyShapeStyle {
        switch style {
        case .tinted: return AnyShapeStyle(Color.white)
        default: return AnyShapeStyle(LinearGradient(colors: [BrandColor.warm, BrandColor.warmDeep], startPoint: .top, endPoint: .bottom))
        }
    }
}

/// App icon artwork at 1024 x 1024 (the system applies the corner mask). iOS 18 variants: light, dark, tinted.
public struct AppIconArt: View {
    public enum Variant { case light, dark, tinted }
    let variant: Variant
    public init(_ variant: Variant) { self.variant = variant }
    public var body: some View {
        ZStack {
            switch variant {
            case .light:
                Rectangle().fill(BrandColor.background)
                RadialGradient(colors: [Color.white.opacity(0.16), .clear], center: .topLeading, startRadius: 0, endRadius: 900)
                KinMark(size: 1024, style: .onBlue)
            case .dark:
                Color.clear
                KinMark(size: 1024, style: .onDark)
            case .tinted:
                Color.clear
                KinMark(size: 1024, style: .tinted).grayscale(1)
            }
        }
        .frame(width: 1024, height: 1024)
    }
}

/// "KIN" set in SF Pro Rounded next to the mark.
public struct Wordmark: View {
    let height: CGFloat
    let onDark: Bool
    public init(height: CGFloat, onDark: Bool = true) { self.height = height; self.onDark = onDark }
    public var body: some View {
        HStack(spacing: height * 0.28) {
            ZStack {
                RoundedRectangle(cornerRadius: height * 0.23, style: .continuous).fill(BrandColor.background)
                KinMark(size: height, style: .onBlue)
            }
            .frame(width: height, height: height)
            Text("KIN").font(.system(size: height * 0.62, weight: .bold, design: .rounded)).tracking(height * 0.04)
                .foregroundStyle(onDark ? Color.white : Color(hex: 0x050505))
        }
    }
}

/// What the launch screen looks like: the background color and the mark, centered (no text, per the HIG).
public struct LaunchScreenPreview: View {
    let dark: Bool
    public init(dark: Bool) { self.dark = dark }
    public var body: some View {
        ZStack {
            (dark ? Color(hex: 0x18191A) : Color(hex: 0xF0F2F5)).ignoresSafeArea()
            ZStack {
                RoundedRectangle(cornerRadius: 26, style: .continuous).fill(BrandColor.background)
                KinMark(size: 112, style: .onBlue)
            }
            .frame(width: 112, height: 112)
        }
    }
}

/// The launch-screen image asset: the mark in its rounded blue tile, transparent around it.
public struct LaunchMarkArt: View {
    public init() {}
    public var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 26, style: .continuous).fill(BrandColor.background)
            KinMark(size: 112, style: .onBlue)
        }
        .frame(width: 112, height: 112)
    }
}
