import SwiftUI
import UIKit

/// KIN's SMS number (design app-07): text KIN your news so it knows who has not heard it yet. "What KIN understood"
/// lists my own facts that came from texts (GET /api/me/facts, source_kind "message"), and "From your calls" every
/// other fact about me, each correctable or deletable (PRODUCT: see, correct and delete what KIN holds about you).
struct MessagesScreen: View {
    let api: KinAPI
    @State private var number: String?
    @State private var understood: [FactRow]?
    @State private var fromCalls: [FactRow]?
    @State private var error: String?
    @State private var editing: FactRow?
    @State private var draft = ""
    @State private var confirm: ConfirmDelete?

    var body: some View {
        MessagesView(number: number, understood: understood, error: error, fromCalls: fromCalls,
                     onEdit: { draft = $0.text; editing = $0 },
                     onDelete: { fact in
                         confirm = ConfirmDelete(title: "Delete \u{201C}\(fact.text)\u{201D}?", button: "Delete") {
                             Task { await act { try await api.deleteFact(fact.id) } }
                         }
                     },
                     retry: { Task { await load() } })
            .task { await load() }
            .refreshable { await load() }
            .confirmDelete($confirm)
            .alert("Edit what KIN understood", isPresented: Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })) {
                TextField("Your news", text: $draft)
                Button("Save") {
                    guard let fact = editing else { return }
                    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !text.isEmpty else { return }
                    Task { await act { _ = try await api.correctFact(fact.id, text: text) } }
                }
                Button("Cancel", role: .cancel) {}
            }
    }

    private func act(_ change: () async throws -> Void) async {
        do { try await change(); await load() } catch { self.error = error.localizedDescription }
    }

    private func load() async {
        do {
            async let n = api.smsNumber()
            async let f = api.facts()
            // The sign-up reply carries the number; GET /api/me does not yet (see the MeSms note).
            let saved = UserDefaults.standard.string(forKey: Self.savedNumberKey)
            let fetched = try await n
            number = saved?.isEmpty == false ? saved : fetched
            let facts = try await f
            understood = Self.fromTexts(facts)
            fromCalls = Self.fromCalls(facts)
            error = nil
        } catch { self.error = "Could not load your messages: \(error.localizedDescription)" }
    }

    /// Where SignupView should save UserOut.sms_number.
    nonisolated static let savedNumberKey = "kin.smsNumber"  // a constant key; readable from any isolation (tests, sign-up)

    /// backend/app/world/sms.py applies texts with source_kind "message".
    static func fromTexts(_ facts: FactsOut) -> [FactRow] { facts.aboutMe.filter { $0.sourceKind == "message" } }
    /// Everything else about me: said on calls (and planted or tapped-in facts, which stand for calls).
    static func fromCalls(_ facts: FactsOut) -> [FactRow] { facts.aboutMe.filter { $0.sourceKind != "message" } }
}

struct MessagesView: View {
    let number: String?
    let understood: [FactRow]?
    let error: String?
    var fromCalls: [FactRow]? = nil
    let onEdit: (FactRow) -> Void
    let onDelete: (FactRow) -> Void
    let retry: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                intro
                if let error { LoadError(message: error, retry: retry) }
                KinSection(title: "What KIN understood",
                           footer: "Private to you. KIN never forwards your texts or shows them to anyone; they only tell KIN your news.") {
                    if let understood, understood.isEmpty {
                        Text("Nothing yet. Text KIN a line about your life.").font(KinFont.subhead).foregroundStyle(K.text2)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(14)
                    }
                    ForEach(Array((understood ?? []).enumerated()), id: \.element.id) { i, f in
                        if i > 0 { Hairline() }
                        row(f)
                    }
                }
                if let fromCalls, !fromCalls.isEmpty {
                    KinSection(title: "From your calls",
                               footer: "What KIN keeps about you from your calls. Correct it or delete it; deleted means gone.") {
                        ForEach(Array(fromCalls.enumerated()), id: \.element.id) { i, f in
                            if i > 0 { Hairline() }
                            row(f)
                        }
                    }
                }
            }
            .padding(.top, 8).padding(.bottom, 24)
        }
        .background(K.grouped)
        .navigationTitle("Messages")
    }

    private var intro: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Text KIN your news").font(KinFont.title3).foregroundStyle(K.text)
            Text("A line is enough. KIN remembers it so the right people hear it from you, on your next call.")
                .font(KinFont.subhead).foregroundStyle(K.text2).fixedSize(horizontal: false, vertical: true)
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("KIN's number").font(KinFont.footnote).foregroundStyle(K.text3)
                    Text(number?.isEmpty == false ? number! : "Not set up on this server")
                        .font(.system(.title3, design: .rounded, weight: .semibold)).monospacedDigit()
                        .foregroundStyle(number?.isEmpty == false ? AnyShapeStyle(K.text) : AnyShapeStyle(K.text3))
                        .lineLimit(1).minimumScaleFactor(0.8)
                }
                Spacer()
                if let number, !number.isEmpty {
                    Button { UIPasteboard.general.string = number } label: {
                        HStack(spacing: 6) { Image(systemName: "doc.on.doc"); Text("Copy") }
                            .font(KinFont.subheadEmph).foregroundStyle(K.link)
                            .padding(.horizontal, 14).frame(height: 36).background(K.primarySoft, in: Capsule())
                            .frame(minHeight: 44)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Copy KIN's number")
                }
            }
            .padding(14).background(K.raised, in: RoundedRectangle(cornerRadius: Radius.image, style: .continuous))
            VStack(alignment: .trailing, spacing: 6) {
                bubble("started bouldering at the campus gym", mine: true)
                bubble("Got it: you started bouldering.", mine: false)
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Example: you text started bouldering at the campus gym, KIN replies Got it.")
        }
        .padding(16).background(K.surface, in: RoundedRectangle(cornerRadius: Radius.section, style: .continuous))
        .padding(.horizontal, Space.gutter)
    }

    private func bubble(_ t: String, mine: Bool) -> some View {
        Text(t).font(KinFont.subhead).foregroundStyle(mine ? AnyShapeStyle(Color.white) : AnyShapeStyle(K.text))
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(mine ? AnyShapeStyle(K.primary) : AnyShapeStyle(K.separator),
                        in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .frame(maxWidth: .infinity, alignment: mine ? .trailing : .leading)
    }

    private func row(_ f: FactRow) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(f.text.prefix(1).uppercased() + f.text.dropFirst()).font(KinFont.headline).foregroundStyle(K.text)
                Text(Self.heard(f)).font(KinFont.footnote).foregroundStyle(K.text3)
            }
            Spacer()
            Menu {
                Button("Edit", systemImage: "pencil") { onEdit(f) }
                Button("Delete", systemImage: "trash", role: .destructive) { onDelete(f) }
            } label: {
                Text("Edit").font(KinFont.subheadEmph).foregroundStyle(K.link).frame(minWidth: 44, minHeight: 44)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
    }

    /// "Texted Oct 3" (or "Said Oct 3" for call facts), plus who has heard it from you (the disclosure view in one line).
    static func heard(_ f: FactRow) -> String {
        let others = f.heardBy.filter { $0.person != f.subject }.map(\.name)
        return (f.sourceKind == "message" ? "Texted " : "Said ") + f.day
            + (others.isEmpty ? "" : " \u{00B7} \(others.joined(separator: ", ")) heard it")
    }
}
