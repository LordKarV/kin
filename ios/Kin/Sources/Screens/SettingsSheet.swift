import SwiftUI

/// People's gear: change your name and the language you speak (PATCH /api/me), sign out.
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
    @State private var name = ""
    @State private var savingName = false
    @State private var nameSaved = false
    @State private var nameError: String?

    private var trimmedName: String { name.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 22) {
                    KinSection(title: "Your name", footer: "Everyone you talk to sees it. Takes effect on your next call.") {
                        nameEditor
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

    private var nameEditor: some View {
        VStack(alignment: .leading, spacing: 12) {
            TextField("Your name", text: $name)
                .font(KinFont.body).foregroundStyle(K.text)
                .textInputAutocapitalization(.words).autocorrectionDisabled()
                .disabled(me == nil || savingName)
                .onChange(of: name) { nameSaved = false }
            CapsuleButton(title: "Save", symbol: "checkmark", busy: savingName) { Task { await saveName() } }
                .disabled(me == nil || trimmedName.isEmpty || trimmedName == me?.name || savingName)
            if let nameError {
                Text(nameError).font(KinFont.subhead).foregroundStyle(K.error)
            } else if nameSaved {
                Text("Saved.").font(KinFont.subhead).foregroundStyle(K.text2)
            }
        }
        .padding(14)
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
            name = mine.name
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

    private func saveName() async {
        savingName = true
        defer { savingName = false }
        do {
            let updated = try await model.api.setName(trimmedName)
            me = updated
            name = updated.name
            nameSaved = true
            nameError = nil
            onSaved()  // People reloads, so the new name shows at once
        } catch {
            if !model.signOutIfBadToken(error) { nameError = "Could not save your name: \(error.localizedDescription)" }
        }
    }
}
