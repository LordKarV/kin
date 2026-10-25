import SwiftUI

// States around a call: waiting for the other person, joining from an invite, the welcome after sign-up, the end of
// a call, adding a relative, and deleting your account. Wording is warm and plain; nothing blames or rushes anyone.

/// You started a call and the other person has not joined yet. One obvious action: share the invite.
public struct WaitingScreen: View {
    let name: String
    public init(name: String) { self.name = name }
    public var body: some View {
        ZStack {
            VideoPlaceholder(.arjun).ignoresSafeArea()
            Color.black.opacity(0.35).ignoresSafeArea()
            VStack(spacing: 0) {
                HStack { KinIndicator(.on); Spacer() }.padding(.horizontal, Space.gutter)
                Spacer()
                VStack(spacing: 14) {
                    Avatar("美", hue: Cast.mei.hue, size: 64)
                        .overlay(Circle().stroke(Color.white.opacity(0.35), lineWidth: 6).padding(-8))
                    Text("Waiting for \(name)").font(KinFont.title2).foregroundStyle(.white)
                    Text("Send \(name) the link. Joining takes about 20 seconds, even the first time.")
                        .font(KinFont.subhead).foregroundStyle(K.Call.text2).multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                    HStack(spacing: 10) {
                        HStack(spacing: 8) { Image(systemName: "square.and.arrow.up"); Text("Share invite") }
                            .font(KinFont.headline).foregroundStyle(.white)
                            .frame(maxWidth: .infinity).frame(height: 52).background(K.Call.mine, in: Capsule())
                        HStack(spacing: 8) { Image(systemName: "link"); Text("Copy") }
                            .font(KinFont.headline).foregroundStyle(.white)
                            .frame(width: 112, height: 52).background(Color.white.opacity(0.16), in: Capsule())
                    }
                    .padding(.top, 6)
                }
                .padding(.horizontal, Space.l)
                Spacer()
                CallControls().padding(.horizontal, Space.gutter)
            }
            .padding(.top, Device.topInset + 4).padding(.bottom, Device.bottomInset + 10)
        }
        .environment(\.colorScheme, .dark)
    }
}

/// Someone opened an invite before having KIN: sign-up and joining are the same 20 seconds.
public struct InvitedSignupScreen: View {
    public init() {}
    public var body: some View {
        SetupStep(step: 1, title: "Arjun invited you to a call", subtitle: "Tell KIN your name and language, and you're in.") {
            VStack(alignment: .leading, spacing: 24) {
                HStack(spacing: 12) {
                    Avatar("A", hue: Cast.arjun.hue, size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Arjun").font(KinFont.headline).foregroundStyle(K.text)
                        Text("Calling from Austin · 10:04 AM").font(KinFont.footnote).foregroundStyle(K.text3)
                    }
                    Spacer()
                    Image(systemName: "video.fill").foregroundStyle(K.link)
                }
                .padding(14).background(K.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                FieldBox("Your name", value: "Mei")
                VStack(alignment: .leading, spacing: 10) {
                    Text("Languages you speak").font(KinFont.subheadEmph).foregroundStyle(K.text2)
                    FlowLayout(spacing: 8) { ChoiceChip("中文", selected: true); ChoiceChip("English", selected: true); ChoiceChip("粤语") }
                    Text("You'll see Arjun in captions in your language.")
                        .font(KinFont.footnote).foregroundStyle(K.text3)
                }
            }
        } footer: {
            VStack(spacing: 10) {
                PrimaryButton("Join Arjun's call", symbol: "video.fill")
                Text("You'll see KIN is on during the call, and you can pause it anytime.")
                    .font(KinFont.footnote).foregroundStyle(K.text3).multilineTextAlignment(.center).frame(maxWidth: .infinity)
            }
        }
    }
}

/// Right after sign-up: the SMS number, explained once, with no pressure to use it.
public struct WelcomeScreen: View {
    public init() {}
    public var body: some View {
        ZStack {
            Rectangle().fill(K.grouped).ignoresSafeArea()
            VStack(alignment: .leading, spacing: 0) {
                Spacer().frame(height: 40)
                Image(systemName: "hand.wave.fill").font(.system(size: 30)).foregroundStyle(K.link)
                    .frame(width: 64, height: 64).background(K.primarySoft, in: Circle())
                Text("You're in, Arjun").font(KinFont.title).foregroundStyle(K.text).padding(.top, 18)
                Text("One optional thing: KIN has a number you can text your news to.")
                    .font(KinFont.body).foregroundStyle(K.text2).padding(.top, 8).fixedSize(horizontal: false, vertical: true)
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Text("+1 (512) 555-0142").font(.system(size: 20, weight: .semibold, design: .rounded)).monospacedDigit().foregroundStyle(K.text)
                        Spacer()
                        HStack(spacing: 6) { Image(systemName: "doc.on.doc"); Text("Copy") }
                            .font(KinFont.subheadEmph).foregroundStyle(K.link)
                            .padding(.horizontal, 14).frame(height: 36).background(K.primarySoft, in: Capsule())
                    }
                    Text("Something like \u{201C}started bouldering\u{201D} is enough. Texts stay private: KIN never forwards them, it just remembers who hasn't heard your news yet.")
                        .font(KinFont.footnote).foregroundStyle(K.text2).fixedSize(horizontal: false, vertical: true)
                }
                .padding(16).background(K.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous)).padding(.top, 24)
                Spacer()
                PrimaryButton("Continue")
                Text("Maybe later is fine too.").font(KinFont.footnote).foregroundStyle(K.text3)
                    .frame(maxWidth: .infinity).padding(.top, 10)
            }
            .padding(.horizontal, Space.l).padding(.top, Device.topInset).padding(.bottom, Device.bottomInset + 12)
        }
    }
}

/// The end of a call. No ratings, no "call again soon": just what KIN picked up, so you can correct it.
public struct CallEndedScreen: View {
    public init() {}
    public var body: some View {
        ZStack {
            Rectangle().fill(K.grouped).ignoresSafeArea()
            VStack(spacing: 0) {
                VStack(spacing: 8) {
                    Avatar("美", hue: Cast.mei.hue, size: 72)
                    Text("Call with Mei").font(KinFont.title2).foregroundStyle(K.text)
                    Text("24 minutes · Sep 14").font(KinFont.subhead).foregroundStyle(K.text2)
                }
                .padding(.top, 48)
                KinSection("New in Mei's world", footer: "Only what was said on this call, and only you see this list. Anything wrong? Tap it to fix or remove.") {
                    HStack(alignment: .top, spacing: 12) {
                        Avatar("林", hue: Cast.lin.hue, size: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text("Lin").font(KinFont.headline).foregroundStyle(K.text)
                                Text("林").font(KinFont.subhead).foregroundStyle(K.text3)
                            }
                            Text("Mei's friend from the Fudan climbing wall").font(KinFont.subhead).foregroundStyle(K.text2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer()
                        Image(systemName: "checkmark.circle.fill").font(.system(size: 20)).foregroundStyle(K.success)
                            .accessibilityLabel("Looks right")
                    }
                    .padding(14)
                    Hairline(inset: 62)
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "mappin.and.ellipse").font(.system(size: 15, weight: .semibold)).foregroundStyle(K.text2)
                            .frame(width: 36, height: 36).background(K.raised, in: Circle())
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Moganshan trip").font(KinFont.headline).foregroundStyle(K.text)
                            Text("Mei and Lin are planning it").font(KinFont.subhead).foregroundStyle(K.text2)
                        }
                        Spacer()
                        Image(systemName: "pencil").font(.system(size: 15, weight: .semibold)).foregroundStyle(K.text3)
                            .frame(width: 32, height: 32)
                    }
                    .padding(14)
                }
                .padding(.top, 28)
                Spacer()
                PrimaryButton("Done").padding(.horizontal, Space.l)
            }
            .padding(.top, Device.topInset).padding(.bottom, Device.bottomInset + 12)
        }
    }
}

/// Placing a relative by hand (film state S6): one name, one relation from the language's kinship table, optional
/// details, and the word the family actually uses.
public struct AddRelativeScreen: View {
    public init() {}
    public var body: some View {
        SheetOver(background: { PeopleScreen(contacts: Sample.contacts) }) {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text("Cancel").font(KinFont.body).foregroundStyle(K.link)
                    Spacer()
                    Text("Add family").font(KinFont.headline).foregroundStyle(K.text)
                    Spacer()
                    Text("Cancel").font(KinFont.body).hidden()
                }
                FieldBox("Their name", value: "Ravi")
                VStack(alignment: .leading, spacing: 10) {
                    Text("Who is Ravi to you?").font(KinFont.subheadEmph).foregroundStyle(K.text2)
                    FlowLayout(spacing: 8) {
                        ChoiceChip("Mom's younger brother", selected: true); ChoiceChip("Mom's elder brother")
                        ChoiceChip("Dad's elder brother"); ChoiceChip("Dad's younger brother"); ChoiceChip("Another relative")
                    }
                }
                FieldBox("What do you call him?", value: "Ravi mama")
                FieldBox("Where does he live? (optional)", value: "Adyar, Chennai")
                PrimaryButton("Add Ravi mama").padding(.top, 4)
            }
        }
    }
}

/// Deleting your account: clear and calm, with an equally prominent way out.
public struct DeleteConfirmScreen: View {
    public init() {}
    public var body: some View {
        SheetOver(background: { YouScreen(facts: Sample.myFacts, thirdParty: Sample.thirdParty, contacts: Sample.contacts) }) {
            VStack(spacing: 14) {
                Image(systemName: "trash").font(.system(size: 22, weight: .semibold)).foregroundStyle(K.error)
                    .frame(width: 56, height: 56).background(K.raised, in: Circle())
                Text("Delete everything about you?").font(KinFont.title3).foregroundStyle(K.text).multilineTextAlignment(.center)
                Text("This removes your account, what you've said on KIN calls, your texts, and everything KIN learned about you. It can't be undone.")
                    .font(KinFont.subhead).foregroundStyle(K.text2).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                VStack(spacing: 10) {
                    Text("Delete everything").font(KinFont.headline).foregroundStyle(K.error)
                        .frame(maxWidth: .infinity).frame(height: 52).background(Color(hex: 0xE41E3F, alpha: 0.1), in: Capsule())
                    SecondaryButton("Keep my account")
                }
                .padding(.top, 6)
            }
            .padding(.top, 6)
        }
    }
}

/// A bottom sheet over a dimmed screen (static stand-in for `.sheet`).
public struct SheetOver<Background: View, Sheet: View>: View {
    let background: Background; let sheet: Sheet
    public init(@ViewBuilder background: () -> Background, @ViewBuilder sheet: () -> Sheet) {
        self.background = background(); self.sheet = sheet()
    }
    public var body: some View {
        ZStack(alignment: .bottom) {
            background
            Color.black.opacity(0.35).ignoresSafeArea()
            VStack(spacing: 0) {
                Capsule().fill(K.separator).frame(width: 36, height: 5).padding(.top, 8).padding(.bottom, 14)
                sheet
            }
            .padding(.horizontal, Space.l)
            .padding(.bottom, Device.bottomInset + 12)
            .frame(maxWidth: .infinity)
            .background(K.surface, in: UnevenRoundedRectangle(topLeadingRadius: 28, topTrailingRadius: 28, style: .continuous))
        }
    }
}
