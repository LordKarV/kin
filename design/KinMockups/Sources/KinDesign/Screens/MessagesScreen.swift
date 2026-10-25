import SwiftUI

/// The SMS number: text KIN your news so it knows who has not heard it yet. Private, never forwarded.
public struct MessagesScreen: View {
    public init() {}
    public var body: some View {
        AppScreen("Messages", tab: .messages) {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Text KIN your news").font(KinFont.title3).foregroundStyle(K.text)
                    Text("A line is enough. KIN remembers it so the right people hear it from you, on your next call.")
                        .font(KinFont.subhead).foregroundStyle(K.text2).fixedSize(horizontal: false, vertical: true)
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("KIN's number").font(KinFont.footnote).foregroundStyle(K.text3)
                            Text("+1 (512) 555-0142").font(.system(size: 20, weight: .semibold, design: .rounded)).monospacedDigit().foregroundStyle(K.text)
                                .lineLimit(1).minimumScaleFactor(0.8)
                        }
                        Spacer()
                        HStack(spacing: 6) { Image(systemName: "doc.on.doc"); Text("Copy") }
                            .font(KinFont.subheadEmph).foregroundStyle(K.link)
                            .padding(.horizontal, 14).frame(height: 36).background(K.primarySoft, in: Capsule())
                    }
                    .padding(14).background(K.raised, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    VStack(alignment: .trailing, spacing: 6) {
                        bubble("started bouldering at the campus gym", mine: true)
                        bubble("Got it, thanks! Noted that you started bouldering.", mine: false)
                    }
                    .frame(maxWidth: .infinity, alignment: .trailing)
                }
                .padding(16).background(K.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, Space.gutter)

                KinSection("What KIN understood", footer: "Private to you. KIN never forwards your texts or shows them to anyone; they only tell KIN your news.") {
                    understood("Started bouldering", "Texted Oct 3")
                    Hairline()
                    understood("Got an internship offer", "Texted Oct 21")
                }
            }
        }
    }

    func bubble(_ t: String, mine: Bool) -> some View {
        Text(t).font(KinFont.subhead).foregroundStyle(mine ? Color.white : Color(hex: 0x050505))
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(mine ? Color(hex: 0x0064E0) : Color(hex: 0xE4E6EB), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .frame(maxWidth: .infinity, alignment: mine ? .trailing : .leading)
    }

    func understood(_ fact: String, _ when: String) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(fact).font(KinFont.headline).foregroundStyle(K.text)
                Text(when).font(KinFont.footnote).foregroundStyle(K.text3)
            }
            Spacer()
            Text("Edit").font(KinFont.subheadEmph).foregroundStyle(K.link).frame(minHeight: 44)
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
    }
}
