import SwiftUI

let langName = ["en": "English", "ta": "Tamil", "zh": "Mandarin", "hi": "Hindi", "es": "Spanish"]

/// The people you call, by circle. No recency nudges ("you haven't called in 3 weeks"): just who they are to you,
/// and what time it is where they are.
public struct PeopleScreen: View {
    let contacts: [Contact]
    let myLang: String
    public init(contacts: [Contact], myLang: String = "en") { self.contacts = contacts; self.myLang = myLang }

    public var body: some View {
        AppScreen("People", tab: .people, trailing: ["person.badge.plus"]) {
            VStack(spacing: 22) {
                section("Family", contacts.filter { $0.circle == "family" })
                section("Friends", contacts.filter { $0.circle == "friends" })
                KinSection("Groups") {
                    HStack(spacing: 12) {
                        ZStack {
                            Avatar("美", hue: Cast.mei.hue, size: 30).offset(x: -8, y: -6)
                            Avatar("P", hue: Cast.priya.hue, size: 30).offset(x: 8, y: 6)
                        }
                        .frame(width: 44, height: 44)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("High school crew").font(KinFont.headline).foregroundStyle(K.text)
                            Text("You, Mei and Priya").font(KinFont.subhead).foregroundStyle(K.text2)
                        }
                        Spacer()
                    }
                    .padding(.horizontal, 14).padding(.vertical, 12)
                }
            }
        }
    }

    @ViewBuilder func section(_ title: String, _ items: [Contact]) -> some View {
        if !items.isEmpty {
            KinSection(title) {
                ForEach(Array(items.enumerated()), id: \.offset) { i, c in
                    if i > 0 { Hairline(inset: 70) }
                    PersonRow(c, showLanguage: c.lang != myLang)
                }
            }
        }
    }
}

public struct PersonRow: View {
    let c: Contact; let showLanguage: Bool
    public init(_ c: Contact, showLanguage: Bool) { self.c = c; self.showLanguage = showLanguage }
    public var body: some View {
        HStack(spacing: 12) {
            Avatar(c.native ?? String(c.name.prefix(1)), hue: hue(c.person), size: 48)
            VStack(alignment: .leading, spacing: 2) {
                Text(c.name).font(KinFont.headline).foregroundStyle(K.text).lineLimit(1)
                Text(c.render).font(KinFont.subhead).foregroundStyle(K.text2).lineLimit(1)
                HStack(spacing: 8) {
                    if let t = c.localTime { Label(c.place.map { "\(t) in \($0)" } ?? t, systemImage: "clock") }
                    if showLanguage { Label(langName[c.lang] ?? c.lang, systemImage: "captions.bubble") }
                }
                .labelStyle(TightLabel()).font(KinFont.footnote).foregroundStyle(K.text3)
            }
            Spacer(minLength: 4)
            CircleIcon("video.fill", tint: K.link, fill: K.raised, size: 40)
        }
        .padding(.leading, 14).padding(.trailing, 4).padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }

    func hue(_ person: String) -> Double {
        person.contains("mei") ? Cast.mei.hue : person.contains("paatti") ? Cast.paatti.hue : person.contains("priya") ? Cast.priya.hue : 0.6
    }
}

struct TightLabel: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 3) { configuration.icon.font(.system(size: 10, weight: .semibold)); configuration.title }
    }
}

/// Nobody yet: say what KIN is and offer exactly one action.
public struct PeopleEmptyScreen: View {
    public init() {}
    public var body: some View {
        AppScreen("People", tab: .people) {
            VStack(spacing: 14) {
                Spacer().frame(height: 120)
                Image(systemName: "person.2.wave.2").font(.system(size: 34, weight: .regular)).foregroundStyle(K.link)
                    .frame(width: 84, height: 84).background(K.primarySoft, in: Circle())
                Text("Who do you want to stay close to?").font(KinFont.title3).foregroundStyle(K.text).multilineTextAlignment(.center)
                Text("Add someone you call. KIN learns the rest from your conversations, so nothing needs setting up.")
                    .font(KinFont.subhead).foregroundStyle(K.text2).multilineTextAlignment(.center).padding(.horizontal, 24)
                PrimaryButton("Add someone", symbol: "plus").frame(width: 220).padding(.top, 8)
            }
            .frame(maxWidth: .infinity)
        }
    }
}
