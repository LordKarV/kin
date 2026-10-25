import SwiftUI

/// Privacy and control in one place: your news and exactly who has heard it (the disclosure view), people from other
/// people's calls with their expiry, private topics, and deleting everything.
public struct YouScreen: View {
    let facts: [MeFact]; let thirdParty: [MeFact]; let contacts: [Contact]
    public init(facts: [MeFact], thirdParty: [MeFact], contacts: [Contact]) { self.facts = facts; self.thirdParty = thirdParty; self.contacts = contacts }

    public var body: some View {
        AppScreen("You", tab: .you) {
            VStack(alignment: .leading, spacing: 22) {
                HStack(spacing: 12) {
                    Avatar("A", hue: Cast.arjun.hue, size: 52)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Arjun").font(KinFont.title3).foregroundStyle(K.text)
                        Text("English, learning Tamil").font(KinFont.subhead).foregroundStyle(K.text2)
                    }
                    Spacer()
                    Text("Edit").font(KinFont.subheadEmph).foregroundStyle(K.link)
                }
                .padding(14).background(K.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, Space.gutter)

                KinSection("Your news, and who has heard it", footer: "KIN uses this to remind you, privately, when your news is relevant to someone who hasn't heard it. It never tells anyone for you.") {
                    ForEach(Array(facts.enumerated()), id: \.offset) { i, f in
                        if i > 0 { Hairline() }
                        disclosureRow(f)
                    }
                }
                KinSection("From other people's calls", footer: "People who aren't on KIN are remembered only by those who heard about them, and are removed after 120 days unless you pin them.") {
                    ForEach(Array(thirdParty.enumerated()), id: \.offset) { i, f in
                        if i > 0 { Hairline() }
                        thirdPartyRow(f)
                    }
                }
                KinSection {
                    HStack {
                        Text("Delete everything KIN knows about you").font(KinFont.body).foregroundStyle(K.error)
                        Spacer()
                    }
                    .padding(.horizontal, 14).frame(height: 50)
                }
            }
        }
    }

    func disclosureRow(_ f: MeFact) -> some View {
        let heard = Set(f.heardBy.map(\.person))
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(f.text).font(KinFont.headline).foregroundStyle(K.text).fixedSize(horizontal: false, vertical: true)
                Spacer()
                Image(systemName: "ellipsis").foregroundStyle(K.text3).frame(width: 32, height: 24)
            }
            HStack(spacing: 6) {
                ForEach(contacts) { c in
                    let has = heard.contains(c.person)
                    HStack(spacing: 4) {
                        Image(systemName: has ? "checkmark" : "minus").font(.system(size: 9, weight: .heavy))
                        Text(c.name.replacingOccurrences(of: "Kamala ", with: ""))
                    }
                    .font(KinFont.captionEmph)
                    .foregroundStyle(has ? K.link : K.text3)
                    .padding(.horizontal, 8).frame(height: 24)
                    .background(has ? K.primarySoft : K.raised, in: Capsule())
                    .accessibilityLabel(has ? "\(c.name) has heard" : "\(c.name) has not heard")
                }
            }
            Text(f.sourceKind == "sms" ? "From your text, \(Self.day(f.saidAt))" : "You said it on a call, \(Self.day(f.saidAt))")
                .font(KinFont.footnote).foregroundStyle(K.text3)
        }
        .padding(14)
    }

    func thirdPartyRow(_ f: MeFact) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: f.sensitiveKind.isEmpty ? "person.crop.circle" : "lock.shield")
                .font(.system(size: 18)).foregroundStyle(K.text2).frame(width: 28)
            VStack(alignment: .leading, spacing: 3) {
                Text(f.text).font(KinFont.subheadEmph).foregroundStyle(K.text).fixedSize(horizontal: false, vertical: true)
                if !f.sensitiveKind.isEmpty {
                    Text("Kept as a topic only. Details are not stored.").font(KinFont.footnote).foregroundStyle(K.text2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(f.pinned ? "Pinned, kept until you remove it" : "Removed \(Self.day(f.expiresAt ?? "")) unless pinned")
                    .font(KinFont.footnote).foregroundStyle(K.text3)
            }
            Spacer()
            Image(systemName: f.pinned ? "pin.fill" : "pin").font(.system(size: 14, weight: .semibold))
                .foregroundStyle(f.pinned ? K.link : K.text3).frame(width: 36, height: 36)
                .accessibilityLabel(f.pinned ? "Unpin" : "Pin")
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
    }

    static func day(_ ymd: String) -> String {
        let s = StorylineCard.month(ymd); return s
    }
}
