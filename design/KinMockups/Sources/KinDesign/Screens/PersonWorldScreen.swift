import SwiftUI

/// A person's world as KIN knows it. It should read like a shared notebook about your friendship, not a dossier:
/// plain sentences, where each one came from, and a way to fix or remove it.
public struct PersonWorldScreen: View {
    public init() {}

    public var body: some View {
        AppScreen(nil) {
            VStack(alignment: .leading, spacing: 22) {
                HStack {
                    CircleIcon("chevron.left", fill: K.grouped)
                    Spacer()
                    CircleIcon("ellipsis", fill: K.grouped)
                }
                .padding(.horizontal, 8)
                VStack(spacing: 6) {
                    Avatar("美", hue: Cast.mei.hue, size: 76)
                    Text("Mei").font(KinFont.title).foregroundStyle(K.text)
                    Text("Close friend from high school").font(KinFont.subhead).foregroundStyle(K.text2)
                    HStack(spacing: 6) {
                        Tag("Mandarin, English", symbol: "captions.bubble")
                        Tag("11:04 PM in Shanghai", symbol: "clock")
                    }
                    .padding(.top, 2)
                    HStack(spacing: 10) {
                        PrimaryButton("Video", symbol: "video.fill")
                        SecondaryButton("Audio", symbol: "phone.fill")
                    }
                    .padding(.top, 12).padding(.horizontal, Space.gutter)
                }
                .frame(maxWidth: .infinity)

                KinSection("People in Mei's life") {
                    item(icon: .avatar("林", Cast.lin.hue), title: "Lin", native: "林", body: "Her friend from the Fudan climbing wall", source: "Mei, Sep 14 call")
                    Hairline(inset: 62)
                    item(icon: .avatar("佐", 0.12), title: "Sato", native: "佐藤", body: "Her dorm roommate", source: "Mei, Oct 2 call")
                }
                KinSection("Catching up") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Job search").font(KinFont.headline).foregroundStyle(K.text)
                            Spacer()
                            Tag("In progress", tint: K.link, fill: K.primarySoft)
                        }
                        MiniTimeline(states: [("Applied to ByteDance", "Sep 2"), ("Second-round interview", "Oct 10")])
                        SourceLine("Mei, Oct 10 call")
                    }
                    .padding(14)
                    Hairline()
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text("Where her parents live").font(KinFont.headline).foregroundStyle(K.text)
                            Spacer()
                            Tag("Unclear", symbol: "exclamationmark.triangle.fill", tint: K.warning, fill: K.raised)
                        }
                        Text("Two calls disagree: moved to Beijing (Sep 20), still in Shanghai (Oct 4).")
                            .font(KinFont.subhead).foregroundStyle(K.text2).fixedSize(horizontal: false, vertical: true)
                        Text("Fix this").font(KinFont.subheadEmph).foregroundStyle(K.link)
                    }
                    .padding(14)
                }
                KinSection(footer: "Built only from what was said on your calls with Mei. Mei has her own version and can correct anything about herself.") {
                    item(icon: .symbol("mappin.and.ellipse"), title: "Shanghai", native: nil, body: "Lives here, studies at Fudan University", source: "You, Sep 14 call")
                }
            }
        }
    }

    enum Icon { case avatar(String, Double), symbol(String) }

    func item(icon: Icon, title: String, native: String?, body: String, source: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            switch icon {
            case .avatar(let t, let h): Avatar(t, hue: h, size: 36)
            case .symbol(let s):
                Image(systemName: s).font(.system(size: 15, weight: .semibold)).foregroundStyle(K.text2)
                    .frame(width: 36, height: 36).background(K.raised, in: Circle())
            }
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(title).font(KinFont.headline).foregroundStyle(K.text)
                    if let native { Text(native).font(KinFont.subhead).foregroundStyle(K.text3) }
                }
                Text(body).font(KinFont.subhead).foregroundStyle(K.text2).fixedSize(horizontal: false, vertical: true)
                SourceLine(source).padding(.top, 2)
            }
            Spacer()
            Image(systemName: "ellipsis").font(.system(size: 15, weight: .semibold)).foregroundStyle(K.text3)
                .frame(width: 32, height: 32).accessibilityLabel("Correct or delete")
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
    }
}

/// Storyline states as a vertical mini timeline (the notebook version of the in-call card).
public struct MiniTimeline: View {
    let states: [(String, String)]
    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(states.enumerated()), id: \.offset) { i, s in
                HStack(alignment: .top, spacing: 10) {
                    VStack(spacing: 0) {
                        Circle().fill(i == states.count - 1 ? K.primary : K.text3).frame(width: 9, height: 9).padding(.top, 5)
                        if i < states.count - 1 { Rectangle().fill(K.separator).frame(width: 2).frame(maxHeight: .infinity) }
                    }
                    .frame(width: 9)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(s.0).font(i == states.count - 1 ? KinFont.subheadEmph : KinFont.subhead).foregroundStyle(K.text)
                        Text(s.1).font(KinFont.footnote).foregroundStyle(K.text3)
                    }
                    .padding(.bottom, i < states.count - 1 ? 10 : 0)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
