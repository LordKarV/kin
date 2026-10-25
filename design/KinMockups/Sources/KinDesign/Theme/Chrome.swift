import SwiftUI

/// iPhone 16 Pro point size. Screens are drawn into this canvas so renders match a real screenshot.
public enum Device {
    public static let size = CGSize(width: 393, height: 852)
    public static let topInset: CGFloat = 59     // Dynamic Island devices
    public static let bottomInset: CGFloat = 34
}

/// Status bar, Dynamic Island and home indicator, drawn so mockup screenshots read as a real phone.
/// In the real app none of this exists (the system draws it); screens only respect the safe areas.
public struct PhoneChrome<Content: View>: View {
    let dark: Bool
    let content: Content
    public init(dark: Bool, @ViewBuilder content: () -> Content) { self.dark = dark; self.content = content() }

    public var body: some View {
        ZStack(alignment: .top) {
            content
            StatusBar(dark: dark)
            Capsule().fill(.black).frame(width: 126, height: 37).padding(.top, 11)
            VStack { Spacer(); Capsule().fill(dark ? Color.white : Color.black).frame(width: 139, height: 5).padding(.bottom, 8) }
        }
        .frame(width: Device.size.width, height: Device.size.height)
        .clipped()
        .environment(\.colorScheme, dark ? .dark : .light)
    }
}

struct StatusBar: View {
    let dark: Bool
    var body: some View {
        HStack {
            Text("9:41").font(.system(size: 17, weight: .semibold)).frame(width: 96)
            Spacer()
            HStack(spacing: 6) {
                Image(systemName: "cellularbars")
                Image(systemName: "wifi")
                Image(systemName: "battery.100").font(.system(size: 19, weight: .regular))
            }
            .font(.system(size: 15, weight: .semibold))
            .frame(width: 96)
        }
        .foregroundStyle(dark ? Color.white : Color.black)
        .padding(.horizontal, 10)
        .padding(.top, 17)
        .frame(height: 54, alignment: .top)
    }
}

/// A ScrollView on iOS. When rendering screenshots on macOS, ImageRenderer does not draw ScrollView contents, so the
/// same content is laid out in a plain stack (the screenshot shows the first screenful, like a real one).
public struct KinScroll<Content: View>: View {
    let content: Content
    public init(@ViewBuilder content: () -> Content) { self.content = content() }
    public var body: some View {
        #if os(iOS)
        ScrollView(showsIndicators: false) { content }
        #else
        TopPinned { VStack(spacing: 0) { content } }.clipped()
        #endif
    }
}

/// Takes exactly the space offered and lays its child out at its natural height from the top (overflow is clipped).
struct TopPinned: Layout {
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        proposal.replacingUnspecifiedDimensions()
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for v in subviews { v.place(at: bounds.origin, anchor: .topLeading, proposal: ProposedViewSize(width: bounds.width, height: nil)) }
    }
}
