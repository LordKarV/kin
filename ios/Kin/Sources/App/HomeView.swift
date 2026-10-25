import SwiftUI

struct HomeView: View {
    @ObservedObject var model: AppModel
    @State private var contacts: [ContactOut] = []
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("KIN").font(.largeTitle.bold())
                Spacer()
                Menu {
                    Button("Sign out", role: .destructive, action: model.signOut)
                } label: { Image(systemName: "ellipsis.circle").font(.title2) }
            }
            Text("People").font(.headline).foregroundStyle(.secondary)
            if contacts.isEmpty {
                Text("Nobody yet. Start a call and share the invite.").foregroundStyle(.secondary)
            }
            ScrollView {
                VStack(spacing: 8) { ForEach(contacts, id: \.person) { ContactRow(contact: $0) } }
            }
            ErrorText(message: error)
            Spacer(minLength: 0)
            PillButton(title: "Start call", systemImage: "video.fill", busy: model.joining) {
                Task { await model.startCall() }
            }
            // An invite names a call, so Share invite lives on the call screen (CallView), not here.
        }
        .padding(24)
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        do { contacts = try await model.api.contacts(); error = nil } catch { self.error = error.localizedDescription }
    }
}

/// One contact: name, how KIN renders them for me, and their circle.
struct ContactRow: View {
    let contact: ContactOut

    var body: some View {
        HStack(spacing: 12) {
            Text(String(contact.name.prefix(1)).uppercased())
                .font(.headline)
                .frame(width: 40, height: 40)
                .background(Theme.primary, in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(contact.name).font(.body.bold())
                if !contact.render.isEmpty { Text(contact.render).font(.footnote).foregroundStyle(.secondary) }
            }
            Spacer()
            Text(contact.circle).font(.caption).foregroundStyle(Theme.accent)
        }
        .padding(12)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.radius))
    }
}
