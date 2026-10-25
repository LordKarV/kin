import SwiftUI

/// Stand-in for a live video frame: a defocused person in a lit room. Mockups only; the real app shows the LiveKit
/// track here. The figure sits where faces sit in a portrait call (upper middle), which is the area cards never cover.
public struct VideoPlaceholder: View {
    public struct Look: Sendable {
        let wall: [Color]; let light: Color; let skin: [Color]; let hair: Color; let top: Color
        public static let mei = Look(wall: [Color(hex: 0x3B4A5A), Color(hex: 0x1D252E)], light: Color(hex: 0xFFE2B8),
                                     skin: [Color(hex: 0xE9C2A0), Color(hex: 0xC99B78)], hair: Color(hex: 0x1C1714), top: Color(hex: 0x6E8FA6))
        public static let paatti = Look(wall: [Color(hex: 0x5A4632), Color(hex: 0x2A2017)], light: Color(hex: 0xFFD08A),
                                        skin: [Color(hex: 0xA77355), Color(hex: 0x7E5238)], hair: Color(hex: 0xBDB6AE), top: Color(hex: 0x9C3B4E))
        public static let arjun = Look(wall: [Color(hex: 0x2F3B33), Color(hex: 0x161C18)], light: Color(hex: 0xE8F0FF),
                                       skin: [Color(hex: 0xB07F5E), Color(hex: 0x8A5E42)], hair: Color(hex: 0x15110E), top: Color(hex: 0x3D4E7A))
        public static let priya = Look(wall: [Color(hex: 0x4A3B52), Color(hex: 0x221B27)], light: Color(hex: 0xFFE9D0),
                                       skin: [Color(hex: 0xB98563), Color(hex: 0x946446)], hair: Color(hex: 0x1A1210), top: Color(hex: 0xC9A15A))
    }
    let look: Look
    public init(_ look: Look) { self.look = look }

    public var body: some View {
        GeometryReader { g in
            let w = g.size.width, h = g.size.height, blur = max(4, w * 0.035)
            ZStack {
                LinearGradient(colors: look.wall, startPoint: .topTrailing, endPoint: .bottomLeading)
                // window light and a lamp, defocused like a phone front camera at arm's length
                Ellipse().fill(look.light.opacity(0.6)).frame(width: w * 0.8, height: h * 0.5).position(x: w * 0.05, y: h * 0.18).blur(radius: w * 0.18)
                ForEach(Array([(0.74, 0.10, 0.09), (0.88, 0.17, 0.06), (0.97, 0.08, 0.08), (0.80, 0.22, 0.05)].enumerated()), id: \.offset) { _, b in
                    Circle().fill(look.light.opacity(0.18)).frame(width: w * b.2).position(x: w * b.0, y: h * b.1).blur(radius: w * 0.02)
                }
                RoundedRectangle(cornerRadius: 8).fill(Color.black.opacity(0.22)).frame(width: w * 0.5, height: h * 0.06)
                    .position(x: w * 0.92, y: h * 0.27).blur(radius: blur)
                // the person: head in the upper third, shoulders from about 47% down
                Group {
                    Ellipse().fill(look.top).frame(width: w * 1.1, height: h * 0.55).position(x: w * 0.5, y: h * 0.80)
                    Capsule().fill(look.skin[1]).frame(width: w * 0.16, height: h * 0.09).position(x: w * 0.5, y: h * 0.45)
                    Ellipse().fill(look.hair).frame(width: w * 0.42, height: h * 0.25).position(x: w * 0.5, y: h * 0.295)
                    Ellipse().fill(LinearGradient(colors: look.skin, startPoint: .topLeading, endPoint: .bottomTrailing))
                        .frame(width: w * 0.33, height: h * 0.205).position(x: w * 0.5, y: h * 0.335)
                    Ellipse().fill(look.hair).frame(width: w * 0.36, height: h * 0.09).position(x: w * 0.5, y: h * 0.235)
                }
                .blur(radius: blur)
                RadialGradient(colors: [.clear, .black.opacity(0.35)], center: .center, startRadius: w * 0.4, endRadius: w * 1.1)
            }
        }
        .accessibilityLabel("Video")
    }
}
