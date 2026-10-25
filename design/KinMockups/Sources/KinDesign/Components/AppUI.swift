import SwiftUI

// Shared building blocks for the non-call screens. Light mode by default, dark supported through the tokens.

/// Grouped background, large title, optional trailing action and a tab bar: the frame of every main screen.
public struct AppScreen<Content: View>: View {
    let title: String?
    let tab: KinTabBar.Tab?
    let trailing: [String]
    let content: Content
    public init(_ title: String?, tab: KinTabBar.Tab? = nil, trailing: [String] = [], @ViewBuilder content: () -> Content) {
        self.title = title; self.tab = tab; self.trailing = trailing; self.content = content()
    }
    public var body: some View {
        ZStack(alignment: .bottom) {
            Rectangle().fill(K.grouped).ignoresSafeArea()
            VStack(alignment: .leading, spacing: 0) {
                if let title {
                    HStack(alignment: .center) {
                        Text(title).font(KinFont.largeTitle).foregroundStyle(K.text)
                        Spacer()
                        ForEach(trailing, id: \.self) { CircleIcon($0) }
                    }
                    .padding(.horizontal, Space.gutter).padding(.top, 6).padding(.bottom, 12)
                }
                KinScroll { content.padding(.bottom, tab == nil ? 24 : 100) }
            }
            .padding(.top, Device.topInset)
            if let tab { KinTabBar(selected: tab) }
        }
    }
}

public struct CircleIcon: View {
    let symbol: String; let tint: KinColor; let fill: KinColor; let size: CGFloat
    public init(_ symbol: String, tint: KinColor = K.text, fill: KinColor = K.surface, size: CGFloat = 36) {
        self.symbol = symbol; self.tint = tint; self.fill = fill; self.size = size
    }
    public var body: some View {
        Image(systemName: symbol).font(.system(size: size * 0.44, weight: .semibold)).foregroundStyle(tint)
            .frame(width: size, height: size).background(fill, in: Circle())
            .frame(minWidth: 44, minHeight: 44)
    }
}

public struct KinTabBar: View {
    public enum Tab: String, CaseIterable { case people = "People", messages = "Messages", you = "You" }
    let selected: Tab
    public init(selected: Tab) { self.selected = selected }
    public var body: some View {
        VStack(spacing: 0) {
            Rectangle().fill(K.separator).frame(height: 0.5)
            HStack {
                ForEach(Tab.allCases, id: \.self) { t in
                    VStack(spacing: 3) {
                        Image(systemName: symbol(t, t == selected)).font(.system(size: 22, weight: .regular)).frame(height: 26)
                        Text(t.rawValue).font(.system(size: 10, weight: .medium))
                    }
                    .foregroundStyle(t == selected ? K.link : K.text3)
                    .frame(maxWidth: .infinity)
                }
            }
            .padding(.top, 7).frame(height: 49, alignment: .top)
            Spacer().frame(height: Device.bottomInset)
        }
        .background(K.surface)
    }
    func symbol(_ t: Tab, _ on: Bool) -> String {
        switch t {
        case .people: return on ? "person.2.fill" : "person.2"
        case .messages: return on ? "bubble.left.and.text.bubble.right.fill" : "bubble.left.and.text.bubble.right"
        case .you: return on ? "person.crop.circle.fill" : "person.crop.circle"
        }
    }
}

/// A titled white group, like an inset grouped list section.
public struct KinSection<Content: View>: View {
    let title: String?; let footer: String?; let content: Content
    public init(_ title: String? = nil, footer: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title; self.footer = footer; self.content = content()
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title { Text(title).font(KinFont.subheadEmph).foregroundStyle(K.text2).padding(.horizontal, 4) }
            VStack(spacing: 0) { content }
                .background(K.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            if let footer {
                Text(footer).font(KinFont.footnote).foregroundStyle(K.text3).padding(.horizontal, 4).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, Space.gutter)
    }
}

public struct Hairline: View {
    let inset: CGFloat
    public init(inset: CGFloat = 16) { self.inset = inset }
    public var body: some View { Rectangle().fill(K.separator).frame(height: 0.5).padding(.leading, inset) }
}

/// Small rounded label, e.g. a language ("Tamil") or a status ("Heard").
public struct Tag: View {
    let text: String; let symbol: String?; let tint: KinColor; let fill: KinColor
    public init(_ text: String, symbol: String? = nil, tint: KinColor = K.text2, fill: KinColor = K.raised) {
        self.text = text; self.symbol = symbol; self.tint = tint; self.fill = fill
    }
    public var body: some View {
        HStack(spacing: 4) {
            if let symbol { Image(systemName: symbol).font(.system(size: 10, weight: .bold)) }
            Text(text)
        }
        .font(KinFont.captionEmph).foregroundStyle(tint)
        .padding(.horizontal, 8).frame(height: 22).background(fill, in: Capsule())
    }
}

public struct PrimaryButton: View {
    let title: String; let symbol: String?
    public init(_ title: String, symbol: String? = nil) { self.title = title; self.symbol = symbol }
    public var body: some View {
        HStack(spacing: 8) { if let symbol { Image(systemName: symbol) }; Text(title) }
            .font(KinFont.headline).foregroundStyle(.white)
            .frame(maxWidth: .infinity).frame(height: 52)
            .background(K.primary, in: Capsule())
    }
}

public struct SecondaryButton: View {
    let title: String; let symbol: String?
    public init(_ title: String, symbol: String? = nil) { self.title = title; self.symbol = symbol }
    public var body: some View {
        HStack(spacing: 8) { if let symbol { Image(systemName: symbol) }; Text(title) }
            .font(KinFont.headline).foregroundStyle(K.text)
            .frame(maxWidth: .infinity).frame(height: 52)
            .background(K.surface, in: Capsule())
            .overlay(Capsule().stroke(K.separator, lineWidth: 1))
    }
}

/// Selectable chip (relations, languages). Selection is shown by fill AND a checkmark, never color alone.
public struct ChoiceChip: View {
    let title: String; let selected: Bool
    public init(_ title: String, selected: Bool = false) { self.title = title; self.selected = selected }
    public var body: some View {
        HStack(spacing: 6) {
            if selected { Image(systemName: "checkmark").font(.system(size: 12, weight: .bold)) }
            Text(title)
        }
        .font(KinFont.subheadEmph)
        .foregroundStyle(selected ? K.link : K.text)
        .padding(.horizontal, 14).frame(height: 38)
        .background(selected ? K.primarySoft : K.surface, in: Capsule())
        .overlay(Capsule().stroke(selected ? K.link : K.separator, lineWidth: selected ? 1.5 : 1))
    }
}

/// A text field drawn as the real one would look (static in mockups).
public struct FieldBox: View {
    let label: String; let value: String; let placeholder: String
    public init(_ label: String, value: String, placeholder: String = "") { self.label = label; self.value = value; self.placeholder = placeholder }
    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(KinFont.subheadEmph).foregroundStyle(K.text2)
            HStack {
                Text(value.isEmpty ? placeholder : value).font(KinFont.body).foregroundStyle(value.isEmpty ? K.text3 : K.text)
                Spacer()
            }
            .padding(.horizontal, 14).frame(height: 52)
            .background(K.surface, in: RoundedRectangle(cornerRadius: Radius.field, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Radius.field, style: .continuous).stroke(K.separator, lineWidth: 1))
        }
    }
}

/// "Where did this come from": every remembered item says who said it and when.
public struct SourceLine: View {
    let text: String
    public init(_ text: String) { self.text = text }
    public var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "text.bubble").font(.system(size: 10, weight: .semibold))
            Text(text)
        }
        .font(KinFont.footnote).foregroundStyle(K.text3)
    }
}
