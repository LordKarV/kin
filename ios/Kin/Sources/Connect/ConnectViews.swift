import SwiftUI
import UIKit

/// Add someone by their KIN handle, no invite link: my handle to share, and a field for theirs.
struct AddPersonSheet: View {
    let api: KinAPI
    let onConnected: () -> Void  // reload People: the new contact can be called right away
    @Environment(\.dismiss) private var dismiss
    @State private var myHandle: String?
    @State private var handleError: String?
    @State private var draft = ""
    @State private var sending = false
    @State private var outcome: ConnectOutcome?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 22) {
                    KinSection(title: "Your handle", footer: "Share it so people can add you without a link.") { mine }
                    KinSection(title: "Their KIN handle") { theirs }
                }
                .padding(.top, 8)
            }
            .background(K.grouped)
            .navigationTitle("Add person")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
        .task { await loadHandle() }
    }

    private var mine: some View {
        HStack {
            if let myHandle {
                Text(myHandle).font(.system(.title3, design: .rounded, weight: .semibold)).foregroundStyle(K.text)
                Spacer()
                Button { UIPasteboard.general.string = myHandle } label: {
                    HStack(spacing: 6) { Image(systemName: "doc.on.doc"); Text("Copy") }
                        .font(KinFont.subheadEmph).foregroundStyle(K.link)
                        .padding(.horizontal, 14).frame(height: 36).background(K.primarySoft, in: Capsule())
                        .frame(minHeight: 44)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Copy your handle")
            } else if let handleError {
                Text(handleError).font(KinFont.subhead).foregroundStyle(K.error)
            } else {
                ProgressView()
            }
        }
        .padding(14)
    }

    private var theirs: some View {
        VStack(alignment: .leading, spacing: 12) {
            TextField("e.g. mei-1234", text: $draft)
                .font(KinFont.body).textInputAutocapitalization(.never).autocorrectionDisabled()
                .submitLabel(.send).onSubmit { submit() }
                .padding(.horizontal, 14).padding(.vertical, 10).background(K.raised, in: Capsule())
                .disabled(sending)
            CapsuleButton(title: "Send request", symbol: "paperplane.fill", busy: sending) { submit() }
            if let outcome {
                Text(outcome.message).font(KinFont.subhead)
                    .foregroundStyle(outcome.isError ? AnyShapeStyle(K.error) : AnyShapeStyle(K.text2))
            }
        }
        .padding(14)
    }

    private func submit() {
        guard !sending else { return }
        sending = true
        Task {
            outcome = await ConnectFlow.send(draft, via: api)
            sending = false
            if outcome?.isConnected == true { onConnected() }
        }
    }

    private func loadHandle() async {
        do { myHandle = try await api.myHandle().handle } catch {
            handleError = "Could not load your handle: \(error.localizedDescription)"
        }
    }
}

/// Incoming connect requests at the top of People, each with Accept and Decline.
struct RequestsSection: View {
    let requests: [ConnectRequestOut]
    let onAnswer: (ConnectRequestOut, Bool) -> Void  // true: accept

    var body: some View {
        KinSection(title: "Requests") {
            ForEach(Array(requests.enumerated()), id: \.element.id) { i, r in
                if i > 0 { Hairline(inset: 74) }
                HStack(spacing: 12) {
                    Avatar(text: Avatar.initial(name: r.from.name), size: 48, hue: Avatar.hue(for: r.from.slug))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(r.from.name).font(KinFont.headline).foregroundStyle(K.text).lineLimit(1)
                        Text("Wants to connect").font(KinFont.subhead).foregroundStyle(K.text2)
                    }
                    Spacer(minLength: 4)
                    Button("Decline") { onAnswer(r, false) }
                        .font(KinFont.subheadEmph).foregroundStyle(K.text2).buttonStyle(.plain).frame(minHeight: 44)
                    Button("Accept") { onAnswer(r, true) }
                        .font(KinFont.subheadEmph).foregroundStyle(K.link)
                        .padding(.horizontal, 14).frame(height: 36).background(K.primarySoft, in: Capsule())
                        .buttonStyle(.plain).frame(minHeight: 44)
                }
                .padding(.leading, 14).padding(.trailing, 10).padding(.vertical, 6)
            }
        }
    }
}
