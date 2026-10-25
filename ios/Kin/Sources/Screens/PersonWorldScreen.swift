import SwiftUI

/// A person's world as KIN knows it: a shared notebook, not a dossier. Plain sentences, where each
/// came from, and a way to correct or delete what you said (PATCH/DELETE /api/me/facts/{id},
/// DELETE /api/me/world/people/{slug}).
struct PersonWorldScreen: View {
    @ObservedObject var model: AppModel
    let contact: ContactOut
    @State private var world: PersonWorld?
    @State private var error: String?
    @State private var editing: FactRow?
    @State private var draft = ""
    @State private var confirm: ConfirmDelete?

    var body: some View {
        PersonWorldView(contact: contact, world: world, error: error, joining: model.joining,
                        actions: .init(video: { model.call(contact, video: true) },
                                       audio: { model.call(contact, video: false) },
                                       forget: { slug in
                                           let name = world?.people.first { $0.id == slug }?.person.name ?? slug
                                           confirm = ConfirmDelete(title: "Forget \(name)? This deletes what KIN knows about them.",
                                                                   button: "Forget \(name)") {
                                               Task { await act { _ = try await model.api.forgetPerson(slug) } }
                                           }
                                       },
                                       correct: { fact in draft = fact.text; editing = fact },
                                       delete: { fact in
                                           confirm = ConfirmDelete(title: "Delete \u{201C}\(fact.text)\u{201D}?", button: "Delete") {
                                               Task { await act { try await model.api.deleteFact(fact.id) } }
                                           }
                                       },
                                       retry: { Task { await load() } }))
            .task { await load() }
            .refreshable { await load() }
            .confirmDelete($confirm)
            .alert("Correct this", isPresented: Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })) {
                TextField("What is true", text: $draft)
                Button("Save") {
                    guard let fact = editing else { return }
                    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !text.isEmpty else { return }
                    Task { await act { _ = try await model.api.correctFact(fact.id, text: text) } }
                }
                Button("Cancel", role: .cancel) {}
            }
    }

    private func act(_ change: () async throws -> Void) async {
        do { try await change(); await load() } catch { self.error = error.localizedDescription }
    }

    private func load() async {
        do {
            async let w = model.api.world()
            async let f = model.api.facts()
            world = PersonWorld.build(slug: contact.person, name: contact.name, world: try await w, facts: try await f)
            error = nil
        } catch { self.error = "Could not load \(contact.name)'s world: \(error.localizedDescription)" }
    }
}

struct PersonWorldActions {
    var video: () -> Void = {}
    var audio: () -> Void = {}
    var forget: (String) -> Void = { _ in }
    var correct: (FactRow) -> Void = { _ in }
    var delete: (FactRow) -> Void = { _ in }
    var retry: () -> Void = {}
}

/// Value-only person world.
struct PersonWorldView: View {
    let contact: ContactOut
    let world: PersonWorld?
    let error: String?
    let joining: Bool
    let actions: PersonWorldActions

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                if let error { LoadError(message: error, retry: actions.retry) }
                if let world { sections(world) } else if error == nil { ProgressView().frame(maxWidth: .infinity) }
            }
            .padding(.bottom, 24)
        }
        .background(K.grouped)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var header: some View {
        VStack(spacing: 6) {
            Avatar(text: Avatar.initial(name: contact.name), size: 76, hue: Avatar.hue(for: contact.person))
            Text(contact.name).font(KinFont.title).foregroundStyle(K.text)
            if !contact.render.isEmpty {
                Text(contact.render).font(KinFont.subhead).foregroundStyle(K.text2).multilineTextAlignment(.center)
            }
            Tag(text: languageName(contact.lang), symbol: "captions.bubble").padding(.top, 2)
            HStack(spacing: 10) {
                CapsuleButton(title: "Video", symbol: "video.fill", busy: joining, action: actions.video)
                CapsuleButton(title: "Audio", symbol: "phone.fill", primary: false, action: actions.audio)
            }
            .padding(.top, 12).padding(.horizontal, Space.gutter)
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder private func sections(_ w: PersonWorld) -> some View {
        if !w.people.isEmpty {
            KinSection(title: "People in \(contact.name)'s life") {
                ForEach(Array(w.people.enumerated()), id: \.element.id) { i, p in
                    if i > 0 { Hairline(inset: 62) }
                    row(avatar: p.person.name, hue: Avatar.hue(for: p.person.person), title: p.person.name,
                        body: p.line, source: p.source, showsMenu: !p.person.isUser) {
                        if !p.person.isUser {
                            Button("Forget \(p.person.name)", systemImage: "trash", role: .destructive) { actions.forget(p.id) }
                        }
                    }
                }
            }
        }
        if !w.storylines.isEmpty {
            KinSection(title: "Catching up") {
                ForEach(Array(w.storylines.enumerated()), id: \.element.id) { i, st in
                    if i > 0 { Hairline() }
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(st.title).font(KinFont.headline).foregroundStyle(K.text)
                            Spacer()
                            Tag(text: st.status == "open" || st.status == "active" ? "In progress" : st.status.capitalized,
                                tint: K.link, fill: K.primarySoft)
                        }
                        MiniTimeline(states: st.states.map { ($0.label.prefix(1).uppercased() + $0.label.dropFirst(), StorylineCard.day($0.at)) })
                    }
                    .padding(14)
                }
            }
        }
        if !w.said.isEmpty {
            KinSection(title: "What you've said about \(contact.name)") {
                ForEach(Array(w.said.enumerated()), id: \.element.id) { i, f in
                    if i > 0 { Hairline() }
                    row(avatar: nil, hue: 0, title: f.text, body: nil, source: "You, \(f.day) \(f.sourceKind)") {
                        Button("Correct", systemImage: "pencil") { actions.correct(f) }
                        Button("Delete", systemImage: "trash", role: .destructive) { actions.delete(f) }
                    }
                }
            }
        }
        KinSection(footer: "Built only from what was said on your calls with \(contact.name). \(contact.name) has their own version and can correct anything about themselves.") {
            if w.places.isEmpty && w.people.isEmpty && w.storylines.isEmpty && w.said.isEmpty {
                Text("Nothing yet. KIN learns as you talk.").font(KinFont.subhead).foregroundStyle(K.text2)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(14)
            }
            ForEach(Array(w.places.enumerated()), id: \.element.id) { i, t in
                if i > 0 { Hairline(inset: 62) }
                row(avatar: nil, hue: 0, symbol: "mappin.and.ellipse", title: t.name, body: t.kind.capitalized, source: nil,
                    showsMenu: false) {}
            }
        }
    }

    private func row<Menu: View>(avatar: String?, hue: Double, symbol: String? = nil, title: String, body: String?,
                                 source: String?, showsMenu: Bool = true, @ViewBuilder menu: () -> Menu) -> some View {
        let items = menu()
        return HStack(alignment: .top, spacing: 12) {
            if let avatar {
                Avatar(text: Avatar.initial(name: avatar), size: 36, hue: hue)
            } else if let symbol {
                Image(systemName: symbol).font(.subheadline.weight(.semibold)).foregroundStyle(K.text2)
                    .frame(width: 36, height: 36).background(K.raised, in: Circle())
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(KinFont.headline).foregroundStyle(K.text).fixedSize(horizontal: false, vertical: true)
                if let body { Text(body).font(KinFont.subhead).foregroundStyle(K.text2).fixedSize(horizontal: false, vertical: true) }
                if let source, !source.isEmpty { SourceLine(text: source).padding(.top, 2) }
            }
            Spacer()
            if showsMenu {
                SwiftUI.Menu { items } label: {
                    Image(systemName: "ellipsis").font(.subheadline.weight(.semibold)).foregroundStyle(K.text3)
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("Correct or delete")
            }
        }
        .padding(.leading, 14).padding(.trailing, 4).padding(.vertical, 8)
    }
}

/// Storyline states as a vertical mini timeline (the notebook version of the in-call card).
struct MiniTimeline: View {
    let states: [(String, String)]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(states.enumerated()), id: \.offset) { i, s in
                HStack(alignment: .top, spacing: 10) {
                    VStack(spacing: 0) {
                        Circle().fill(i == states.count - 1 ? AnyShapeStyle(K.primary) : AnyShapeStyle(K.text3))
                            .frame(width: 9, height: 9).padding(.top, 5)
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

/// A permanent delete waits for a second tap: there is no undo on the server.
struct ConfirmDelete: Identifiable {
    let id = UUID()
    let title: String
    let button: String
    let run: () -> Void
}

extension View {
    func confirmDelete(_ pending: Binding<ConfirmDelete?>) -> some View {
        confirmationDialog(pending.wrappedValue?.title ?? "", isPresented: Binding(get: { pending.wrappedValue != nil },
                                                                                set: { if !$0 { pending.wrappedValue = nil } }),
                           titleVisibility: .visible, presenting: pending.wrappedValue) { c in
            Button(c.button, role: .destructive) { c.run() }
            Button("Cancel", role: .cancel) {}
        }
    }
}
