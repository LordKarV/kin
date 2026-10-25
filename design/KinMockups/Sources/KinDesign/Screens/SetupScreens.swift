import SwiftUI

/// First run: about 20 seconds, three short steps, no account wall.
public struct SetupStep<Content: View, Footer: View>: View {
    let step: Int; let title: String; let subtitle: String?
    let content: Content; let footer: Footer
    public init(step: Int, title: String, subtitle: String? = nil, @ViewBuilder content: () -> Content, @ViewBuilder footer: () -> Footer) {
        self.step = step; self.title = title; self.subtitle = subtitle; self.content = content(); self.footer = footer()
    }
    public var body: some View {
        ZStack {
            Rectangle().fill(K.grouped).ignoresSafeArea()
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 6) {
                    ForEach(1...3, id: \.self) { i in
                        Capsule().fill(i <= step ? K.primary : K.separator).frame(height: 4)
                    }
                }
                .padding(.top, 12)
                .accessibilityLabel("Step \(step) of 3")
                Text(title).font(KinFont.title).foregroundStyle(K.text).padding(.top, 28).fixedSize(horizontal: false, vertical: true)
                if let subtitle {
                    Text(subtitle).font(KinFont.body).foregroundStyle(K.text2).padding(.top, 8).fixedSize(horizontal: false, vertical: true)
                }
                content.padding(.top, 28)
                Spacer(minLength: 16)
                footer
            }
            .padding(.horizontal, Space.l)
            .padding(.top, Device.topInset)
            .padding(.bottom, Device.bottomInset + 12)
        }
    }
}

public enum Setup {
    public static var name: some View {
        SetupStep(step: 1, title: "What should people call you?",
                  subtitle: "KIN starts with just you. It learns everyone else from your calls.") {
            VStack(alignment: .leading, spacing: 24) {
                FieldBox("Your name", value: "Arjun")
                VStack(alignment: .leading, spacing: 10) {
                    Text("Languages you speak").font(KinFont.subheadEmph).foregroundStyle(K.text2)
                    FlowLayout(spacing: 8) {
                        ChoiceChip("English", selected: true)
                        ChoiceChip("Tamil, a little", selected: true)
                        ChoiceChip("Hindi")
                        ChoiceChip("Spanish")
                        HStack(spacing: 4) { Image(systemName: "plus"); Text("More") }
                            .font(KinFont.subheadEmph).foregroundStyle(K.link).padding(.horizontal, 14).frame(height: 38)
                    }
                    Text("Captions appear automatically when you and the other person speak different languages.")
                        .font(KinFont.footnote).foregroundStyle(K.text3).fixedSize(horizontal: false, vertical: true)
                }
            }
        } footer: { PrimaryButton("Continue") }
    }

    public static var firstPerson: some View {
        SetupStep(step: 2, title: "Who do you want to call first?") {
            VStack(alignment: .leading, spacing: 22) {
                FieldBox("Their name", value: "Mei")
                VStack(alignment: .leading, spacing: 10) {
                    Text("How do you know Mei?").font(KinFont.subheadEmph).foregroundStyle(K.text2)
                    HStack(spacing: 0) {
                        segment("Family", on: false); segment("Friend", on: true)
                    }
                    .padding(3).background(K.raised, in: Capsule())
                    Text("More specific (optional)").font(KinFont.footnote).foregroundStyle(K.text3).padding(.top, 4)
                    FlowLayout(spacing: 8) {
                        ChoiceChip("Close friend", selected: true); ChoiceChip("Roommate"); ChoiceChip("Classmate")
                        ChoiceChip("Partner"); ChoiceChip("Coworker"); ChoiceChip("Teammate")
                    }
                }
                VStack(alignment: .leading, spacing: 10) {
                    FieldBox("Where you know each other from (optional)", value: "High school")
                }
                VStack(alignment: .leading, spacing: 10) {
                    Text("Mei speaks").font(KinFont.subheadEmph).foregroundStyle(K.text2)
                    FlowLayout(spacing: 8) { ChoiceChip("Mandarin", selected: true); ChoiceChip("English", selected: true); ChoiceChip("Cantonese") }
                }
            }
        } footer: { PrimaryButton("Continue") }
    }

    static func segment(_ t: String, on: Bool) -> some View {
        Text(t).font(KinFont.subheadEmph).foregroundStyle(on ? K.text : K.text2)
            .frame(maxWidth: .infinity).frame(height: 34)
            .background(on ? K.surface : KinColor(light: .clear, dark: .clear), in: Capsule())
            .shadow(color: .black.opacity(on ? 0.08 : 0), radius: 3, y: 1)
    }

    public static var promise: some View {
        SetupStep(step: 3, title: "KIN stays quiet", subtitle: "It speaks only when one of you would be lost.") {
            VStack(alignment: .leading, spacing: 22) {
                promiseRow("waveform", "Just a call, most of the time",
                           "No feed, no topic lists. A short note appears only when a name, a word or some news would leave you lost.")
                promiseRow("eye", "Everyone can see it",
                           "Both of you see when KIN is on, and either of you can pause it for the rest of the call.")
                promiseRow("lock", "Yours to see and delete",
                           "Audio is never kept. You can see, correct or delete anything KIN remembers about you.")
            }
        } footer: {
            VStack(spacing: 10) {
                PrimaryButton("Invite Mei to a call", symbol: "video.fill")
                Text("Mei gets a link. She sets up her own KIN in the same 20 seconds.")
                    .font(KinFont.footnote).foregroundStyle(K.text3).multilineTextAlignment(.center).frame(maxWidth: .infinity)
            }
        }
    }

    static func promiseRow(_ symbol: String, _ title: String, _ body: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: symbol).font(.system(size: 18, weight: .semibold)).foregroundStyle(K.link)
                .frame(width: 40, height: 40).background(K.primarySoft, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(KinFont.headline).foregroundStyle(K.text)
                Text(body).font(KinFont.subhead).foregroundStyle(K.text2).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
