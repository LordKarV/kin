import Contacts
import CryptoKit
import SwiftUI

/// Which of my phone contacts are on KIN (POST /api/connect/match): numbers are normalized and SHA-256 hashed on
/// the phone, only the hashes are sent, and the server keeps none of them.
enum ContactMatch {
    static let maxHashes = 2000  // the server's cap per request

    enum Failure: LocalizedError {
        case denied
        var errorDescription: String? { "Allow Contacts for KIN in Settings to find friends." }
    }

    /// Mirrors backend world.users.normalize_phone exactly: digits only (any Unicode decimal digit), a bare 10
    /// digits without a leading + gets US 1, 8 to 15 digits, then "+" in front (E.164). nil when it is not a number.
    static func normalize(_ raw: String) -> String? {
        let digits = raw.unicodeScalars.filter { $0.properties.numericType == .decimal }
            .compactMap { $0.properties.numericValue }.map { String(Int($0)) }.joined()
        let leadingPlus = raw.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("+")
        // ponytail: bare 10 digits = US, the server's rule; other local formats need a country, add one with it
        let full = digits.count == 10 && !leadingPlus ? "1" + digits : digits
        return (8...15).contains(full.count) ? "+" + full : nil
    }

    /// Lowercase hex SHA-256 of the E.164 string's UTF-8 bytes.
    static func hash(_ e164: String) -> String {
        SHA256.hash(data: Data(e164.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    /// Unique hashes of the numbers that normalize, at most `maxHashes`.
    static func hashes(of numbers: [String]) -> [String] {
        // ponytail: an address book over 2000 numbers is cut, not batched; send several requests if that happens
        Array(Set(numbers.compactMap(normalize).map(hash)).sorted().prefix(maxHashes))
    }

    /// Asks for Contacts access, reads every phone number, and asks KIN which belong to users.
    static func find(via api: KinAPI) async throws -> [MatchedUser] {
        let found = hashes(of: try await phoneNumbers())
        return found.isEmpty ? [] : try await api.matchContacts(hashes: found)
    }

    private static func phoneNumbers() async throws -> [String] {
        let store = CNContactStore()
        guard try await store.requestAccess(for: .contacts) else { throw Failure.denied }
        var numbers: [String] = []
        let request = CNContactFetchRequest(keysToFetch: [CNContactPhoneNumbersKey as CNKeyDescriptor])
        try store.enumerateContacts(with: request) { contact, _ in
            numbers += contact.phoneNumbers.map { $0.value.stringValue }
        }
        return numbers
    }
}

/// The Add person sheet's "Find friends from Contacts" row and what it found.
struct ContactMatchSection: View {
    let api: KinAPI
    let onConnected: () -> Void
    @State private var results: [MatchedUser]?
    @State private var searching = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button(action: find) {
                HStack(spacing: 12) {
                    Image(systemName: "person.crop.circle.badge.plus").font(.title3).foregroundStyle(K.link)
                    Text("Find friends from Contacts").font(KinFont.body).foregroundStyle(K.text)
                    Spacer()
                    if searching { ProgressView() }
                }
                .padding(14).frame(minHeight: 44).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(searching)
            if let error {
                Text(error).font(KinFont.subhead).foregroundStyle(K.error).padding([.horizontal, .bottom], 14)
            }
            if let results, results.isEmpty {
                Text("None of your contacts are on KIN yet.").font(KinFont.subhead).foregroundStyle(K.text2)
                    .padding([.horizontal, .bottom], 14)
            }
            ForEach(results ?? []) { user in
                Hairline(inset: 74)
                row(user)
            }
        }
    }

    private func row(_ user: MatchedUser) -> some View {
        HStack(spacing: 12) {
            Avatar(text: Avatar.initial(name: user.name), size: 48, hue: Avatar.hue(for: user.slug))
            VStack(alignment: .leading, spacing: 2) {
                Text(user.name).font(KinFont.headline).foregroundStyle(K.text).lineLimit(1)
                Text("On KIN").font(KinFont.subhead).foregroundStyle(K.text2)
            }
            Spacer(minLength: 4)
            switch user.relation {
            case "connected": Text("Connected").font(KinFont.subheadEmph).foregroundStyle(K.text2)
            case "requested": Text("Requested").font(KinFont.subheadEmph).foregroundStyle(K.text2)
            default:  // none, or incoming: sending back accepts (backend connect._request)
                Button(user.relation == "incoming" ? "Accept" : "Add") { add(user) }
                    .font(KinFont.subheadEmph).foregroundStyle(K.link)
                    .padding(.horizontal, 14).frame(height: 36).background(K.primarySoft, in: Capsule())
                    .buttonStyle(.plain).frame(minHeight: 44)
            }
        }
        .padding(.leading, 14).padding(.trailing, 10).padding(.vertical, 6)
    }

    private func find() {
        searching = true
        Task {
            do {
                results = try await ContactMatch.find(via: api)
                error = nil
            } catch {
                self.error = (error as? ContactMatch.Failure)?.errorDescription
                    ?? "Could not check your contacts: \(error.localizedDescription)"
            }
            searching = false
        }
    }

    private func add(_ user: MatchedUser) {
        Task {
            do {
                let out = try await api.connect(slug: user.slug)
                let relation = out.status == "accepted" ? "connected" : "requested"
                results = results?.map { $0.slug == user.slug ? MatchedUser(slug: $0.slug, name: $0.name, relation: relation) : $0 }
                error = nil
                if relation == "connected" { onConnected() }
            } catch {
                self.error = "Could not add \(user.name): \(error.localizedDescription)"
            }
        }
    }
}
