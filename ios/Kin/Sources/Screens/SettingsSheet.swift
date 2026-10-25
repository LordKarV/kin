import SwiftUI

/// People's gear: change the language you speak (PATCH /api/me), see your name, sign out.
struct SettingsSheet: View {
    @ObservedObject var model: AppModel
    let onSaved: () -> Void  // reload People: which rows show a language depends on mine
    @Environment(\.dismiss) private var dismiss
    @State private var me: MeOut?
    @State private var languages: [LanguageOut] = []
    @State private var lang = ""
    @State private var saving = false
    @State private var saved = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 22) {
                    KinSection(title: "Your name") {
                        Text(me?.name ?? "").font(KinFont.body).foregroundStyle(K.text)
                            .frame(maxWidth: .infinity, minHeight: 22, alignment: .leading).padding(14)
                    }
                    KinSection(title: "Language you speak", footer: "Takes effect on your next call.") { language }
                    KinSection {
                        Button("Sign out", role: .destructive) { model.signOut() }
                            .font(KinFont.body).frame(maxWidth: .infinity, alignment: .leading).padding(14)
                    }
                }
                .padding(.top, 8)
            }
            .background(K.grouped)
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
        .task { await load() }
    }

    private var language: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker("Language you speak", selection: $lang) {
                ForEach(languages) { Text(SignupView.label($0)).tag($0.code) }
            }
            .pickerStyle(.menu)
            .disabled(languages.isEmpty || saving)
            .onChange(of: lang) { saved = false }
            CapsuleButton(title: "Save", symbol: "checkmark", busy: saving) { Task { await save() } }
                .disabled(me == nil || lang.isEmpty || lang == me?.lang || saving)
            if let error {
                Text(error).font(KinFont.subhead).foregroundStyle(K.error)
            } else if saved {
                Text("Saved.").font(KinFont.subhead).foregroundStyle(K.text2)
            }
        }
        .padding(14)
    }

    private func load() async {
        do {
            let mine = try await model.api.me()
            let all = try await model.api.languages()
            languages = all.sorted { SignupView.label($0) < SignupView.label($1) }
            me = mine
            lang = mine.lang
            error = nil
        } catch {
            if !model.signOutIfBadToken(error) { self.error = "Could not load your settings: \(error.localizedDescription)" }
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        do {
            me = try await model.api.setLanguage(lang)
            saved = true
            error = nil
            onSaved()
        } catch {
            if !model.signOutIfBadToken(error) { self.error = "Could not save your language: \(error.localizedDescription)" }
        }
    }
}
