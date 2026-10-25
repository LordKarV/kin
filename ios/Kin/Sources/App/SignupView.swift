import SwiftUI

struct SignupView: View {
    @ObservedObject var model: AppModel
    @State private var name = ""
    @State private var phone = ""
    @State private var lang = Locale.current.language.languageCode?.identifier ?? "en"
    @State private var languages: [LanguageOut] = []
    @State private var busy = false
    @State private var error: String?
    @State private var done: UserOut?
    @State private var defaultsApplied = false
    #if DEBUG
    @State private var signinLink = ""
    #endif

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("KIN").font(.largeTitle.bold())
                if let done { welcome(done) } else { form }
            }
            .padding(24)
        }
        .task {
            applyBuildDefaults()  // before the language list, so it loads from the default server
            await loadLanguages()
        }
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Calls that keep you in each other's world.").foregroundStyle(.secondary)
            KinField(label: "Your name", text: $name)
            VStack(alignment: .leading, spacing: 6) {
                Text("Language you speak").font(.subheadline).foregroundStyle(.secondary)
                Picker("Language you speak", selection: $lang) {
                    ForEach(languages) { Text(Self.label($0)).tag($0.code) }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(6)
                .background(Theme.field, in: RoundedRectangle(cornerRadius: Theme.radiusSmall))
            }
            KinField(label: "Phone (optional, for texting KIN)", text: $phone, keyboard: .phonePad)
            ErrorText(message: error)
            PillButton(title: model.pendingInvite == nil ? "Sign up" : "Sign up and join", busy: busy) {
                Task { await submit() }
            }
            .disabled(!canSubmit)
            DisclosureGroup("Server") {
                KinField(label: "KIN server", text: $model.baseURLString, keyboard: .URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                ErrorText(message: model.serverAddressError)
                Button("Reload languages") { Task { await loadLanguages() } }.padding(.top, 4)
                #if DEBUG
                // A kin://signin link signs this phone in as that person (debug builds).
                KinField(label: "Sign-in link (debug)", text: $signinLink, keyboard: .URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Sign in with link") { signInWithLink() }
                    .disabled(trimmedLink.isEmpty)
                #endif
            }
            .tint(Theme.accent)
        }
    }

    private func welcome(_ out: UserOut) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("You're in, \(name).").font(.title2.bold())
            if let sms = out.smsNumber, !sms.isEmpty {
                Text("Text your news to KIN at").foregroundStyle(.secondary)
                Text(sms).font(.title3.monospacedDigit()).textSelection(.enabled)
                Text("Messages stay private. KIN only uses them to know what the people you call have not heard yet.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            PillButton(title: "Continue") {
                Self.saveSmsNumber(out)
                model.signedUp(token: out.token)
            }
        }
    }

    /// GET /api/me has no sms_number, so MessagesScreen reads the number saved here first.
    /// The backend sends "" when no number is configured; that clears the key so the fetched value wins.
    static func saveSmsNumber(_ out: UserOut) {
        if let sms = out.smsNumber, !sms.isEmpty {
            UserDefaults.standard.set(sms, forKey: MessagesScreen.savedNumberKey)
        } else {
            UserDefaults.standard.removeObject(forKey: MessagesScreen.savedNumberKey)
        }
    }

    /// A build-time default (project.yml KIN_DEFAULT_SERVER, via Info.plist). nil when empty or left unexpanded.
    static func buildDefault(_ key: String) -> String? {
        let raw = (Bundle.main.object(forInfoDictionaryKey: key) as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let raw, !raw.isEmpty, !raw.contains("$(") else { return nil }
        return raw
    }

    /// A build made for a server (KIN_DEFAULT_SERVER) opens with it filled in. Runs once per sign-up screen.
    private func applyBuildDefaults() {
        guard !defaultsApplied else { return }
        defaultsApplied = true
        if let server = Self.buildDefault("KINDefaultServer") { model.baseURLString = server }
    }

    private var canSubmit: Bool {
        #if DEBUG
        if !trimmedLink.isEmpty { return true }  // signs in with the link: no name or language list needed
        #endif
        return !name.trimmingCharacters(in: .whitespaces).isEmpty && !languages.isEmpty
    }

    #if DEBUG
    private var trimmedLink: String { signinLink.trimmingCharacters(in: .whitespacesAndNewlines) }

    private func signInWithLink() {
        guard let url = URL(string: trimmedLink) else {
            error = "That is not a link."
            return
        }
        model.open(url)
    }
    #endif

    static func label(_ l: LanguageOut) -> String { Locale.current.localizedString(forLanguageCode: l.code) ?? l.name }

    private func loadLanguages() async {
        do {
            let all = try await model.signupAPI.languages()
            languages = all.sorted { Self.label($0) < Self.label($1) }
            if !languages.contains(where: { $0.code == lang }) { lang = languages.first { $0.code == "en" }?.code ?? languages.first?.code ?? "en" }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func submit() async {
        #if DEBUG
        if !trimmedLink.isEmpty { return signInWithLink() }  // a pasted sign-in link
        #endif
        busy = true
        defer { busy = false }
        let p = phone.trimmingCharacters(in: .whitespaces)
        do {
            done = try await model.signupAPI.signup(name: name.trimmingCharacters(in: .whitespaces), lang: lang, phone: p.isEmpty ? nil : p)
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}
