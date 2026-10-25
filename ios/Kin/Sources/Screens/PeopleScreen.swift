import SwiftUI

/// Home after sign-up: People and Messages tabs (design app-04, app-07).
struct MainTabs: View {
    @ObservedObject var model: AppModel

    var body: some View {
        TabView {
            NavigationStack { PeopleScreen(model: model) }
                .tabItem { Label("People", systemImage: "person.2.fill") }
            NavigationStack { MessagesScreen(api: model.api) }
                .tabItem { Label("Messages", systemImage: "bubble.left.and.text.bubble.right.fill") }
        }
        .tint(K.link)
    }
}

/// The people you call, by circle (GET /api/contacts). No recency nudges: just who they are to you.
struct PeopleScreen: View {
    @ObservedObject var model: AppModel
    @State private var contacts: [ContactOut]?
    @State private var error: String?
    @State private var myLang: String?

    var body: some View {
        PeopleList(contacts: contacts, error: error, myLang: myLang, joining: model.joining,
                   onCall: { Task { await model.startCall() } }, onSignOut: model.signOut,
                   retry: { Task { await load() } }) { contact in
            PersonWorldScreen(model: model, contact: contact)
        }
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        do {
            contacts = try await model.api.contacts()
            error = nil
            myLang = try await model.api.me().lang
        } catch {
            self.error = "Could not load your people: \(error.localizedDescription)"
        }
    }
}

/// Value-only People list; `destination` builds a person's world.
struct PeopleList<Destination: View>: View {
    let contacts: [ContactOut]?  // nil while loading
    let error: String?
    let myLang: String?
    let joining: Bool
    let onCall: () -> Void
    var onSignOut: () -> Void = {}
    let retry: () -> Void
    @ViewBuilder let destination: (ContactOut) -> Destination

    static var circles: [(key: String, title: String)] { [("family", "Family"), ("friends", "Friends"), ("group", "Groups")] }

    var body: some View {
        ScrollView {
            VStack(spacing: 22) {
                if let error { LoadError(message: error, retry: retry) }
                if let contacts, contacts.isEmpty { empty }
                ForEach(Self.circles, id: \.key) { circle in
                    let rows = (contacts ?? []).filter { $0.circle == circle.key }
                    if !rows.isEmpty {
                        KinSection(title: circle.title) {
                            ForEach(Array(rows.enumerated()), id: \.element.person) { i, c in
                                if i > 0 { Hairline(inset: 74) }
                                NavigationLink { destination(c) } label: {
                                    PersonRow(contact: c, showLanguage: myLang.map { c.lang != $0 } ?? true, onCall: onCall)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
            }
            .padding(.top, 8).padding(.bottom, 24)
        }
        .background(K.grouped)
        .navigationTitle("People")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button("Start a call", systemImage: "video.badge.plus", action: onCall)
                    Button("Sign out", systemImage: "rectangle.portrait.and.arrow.right", role: .destructive, action: onSignOut)
                } label: { CircleIcon(symbol: "person.badge.plus") }
                .accessibilityLabel("Add someone")
            }
        }
        .overlay { if contacts == nil && error == nil { ProgressView() } }
    }

    /// Nobody yet: what KIN is in one sentence, and exactly one action.
    private var empty: some View {
        VStack(spacing: 14) {
            Spacer().frame(height: 80)
            Image(systemName: "person.2.wave.2").font(.system(size: 34)).foregroundStyle(K.link)
                .frame(width: 84, height: 84).background(K.primarySoft, in: Circle())
            Text("Who do you want to stay close to?").font(KinFont.title3).foregroundStyle(K.text)
                .multilineTextAlignment(.center)
            Text("Start a call and share the invite. KIN learns the rest from your conversations, so nothing needs setting up.")
                .font(KinFont.subhead).foregroundStyle(K.text2).multilineTextAlignment(.center).padding(.horizontal, 24)
            CapsuleButton(title: "Start a call", symbol: "video.fill", busy: joining, action: onCall)
                .frame(width: 220).padding(.top, 8)
        }
        .frame(maxWidth: .infinity)
    }
}

/// One person: who they are to you and their language when it differs. ponytail: the mockup's "11:04 PM in
/// Shanghai" needs a `tz`/place on ContactOut (design-notes "Proposed contract additions"); add it when the server does.
struct PersonRow: View {
    let contact: ContactOut
    let showLanguage: Bool
    let onCall: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Avatar(text: Avatar.initial(name: contact.name), size: 48, hue: Avatar.hue(for: contact.person))
            VStack(alignment: .leading, spacing: 2) {
                Text(contact.name).font(KinFont.headline).foregroundStyle(K.text).lineLimit(1)
                if !contact.render.isEmpty {
                    Text(contact.render).font(KinFont.subhead).foregroundStyle(K.text2).lineLimit(1)
                }
                if showLanguage {
                    Label(languageName(contact.lang), systemImage: "captions.bubble")
                        .font(KinFont.footnote).foregroundStyle(K.text3)
                }
            }
            Spacer(minLength: 4)
            Button(action: onCall) { CircleIcon(symbol: "video.fill", tint: K.link, fill: K.raised, size: 40) }
                .buttonStyle(.plain)
                .accessibilityLabel("Start a call")
        }
        .padding(.leading, 14).padding(.trailing, 4).padding(.vertical, 6)
        .contentShape(Rectangle())
    }
}
