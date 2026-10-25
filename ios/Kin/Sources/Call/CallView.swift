import SwiftUI

/// The one call screen (docs/ARCHITECTURE.md 8, 9.1): same for everyone, no roles. Feeds `kin` messages through the
/// pure reducer and turns taps into CallController / REST calls. All drawing is in `CallScreen`, which takes values.
struct CallView: View {
    @ObservedObject var call: CallController
    let invite: URL?
    @State private var world = WorldState()

    /// ponytail: CallController keeps its KinAPI private and has no place(); this rebuilds the same client AppModel
    /// uses (debug base URL default + Keychain). Replace with a CallController.place once it exists.
    private var api: KinAPI {
        let base = UserDefaults.standard.string(forKey: "kin.baseURL").flatMap(URL.init(string:))
            ?? URL(string: AppModel.defaultBaseURL)!
        return KinAPI(baseURL: base, token: Keychain.get("token"), apiKey: Keychain.get("apiKey"))
    }

    var body: some View {
        CallScreen(
            world: world, peers: call.peers, me: call.selfTile, myPerson: call.join.person,
            kinOn: !call.isPaused, pausedBy: call.pausedBy,
            micOn: call.micOn, cameraOn: call.cameraOn, voiceOn: call.voiceOn,
            invite: invite, error: call.lastError ?? world.error,
            actions: CallActions(
                pause: { paused in Task { await call.setPaused(paused) } },
                mic: { on in Task { await call.setMic(on) } },
                camera: { on in Task { await call.setCamera(on) } },
                voice: { on in Task { await call.setVoice(on) } },
                hangUp: { Task { await call.hangUp() } },
                send: { text in Task { await call.typeText(text) } },
                card: handle))
        .task {
            world.participants = call.participants  // messages() does not replay `joined`; names work from the start
            for await msg in call.messages() { world = reduce(world, msg, me: call.me, now: .now) }
        }
        .task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                world = expire(world, now: .now)
            }
        }
    }

    private func handle(_ card: RailCard, _ action: CardAction) {
        switch action {
        case .touch(let on):
            world = touch(world, key: card.key, touching: on, now: .now)
        case .know, .dismiss:
            world = remove(world, key: card.key)
            Task { await call.feedback(key: card.key, action: action == .know ? .know : .dismiss) }
        case .place(let s):
            guard case .glance(let g, _) = card.content else { return }
            let body = PlaceIn(name: g.term.isEmpty ? g.title : g.term, owner: s.owner, relation: s.relation,
                               callId: call.callId)
            world = remove(world, key: card.key)  // optimistic: a second tap cannot place twice
            world.error = nil
            Task {
                do { _ = try await api.place(body) } catch {
                    world.dismissed.remove(card.key)
                    world.rail.insert(card, at: 0)
                    world.error = "Could not add \(body.name ?? "them"): \(error.localizedDescription)"
                }
            }
        }
    }
}

/// Every control on the call screen as a closure, so `CallScreen` stays a value-only view.
struct CallActions {
    var pause: (Bool) -> Void = { _ in }
    var mic: (Bool) -> Void = { _ in }
    var camera: (Bool) -> Void = { _ in }
    var voice: (Bool) -> Void = { _ in }
    var hangUp: () -> Void = {}
    var send: (String) -> Void = { _ in }
    var card: (RailCard, CardAction) -> Void = { _, _ in }
}

/// One-to-one first: large remote video with my small self view (TilesView), the caption line under it (never over
/// faces), the card rail, typed input, then controls. The KIN indicator is always visible.
struct CallScreen: View {
    let world: WorldState
    let peers: [Tile]
    let me: Tile?
    let myPerson: String
    let kinOn: Bool
    let pausedBy: PausedBy?
    let micOn: Bool
    let cameraOn: Bool
    let voiceOn: Bool
    let invite: URL?
    let error: String?
    let actions: CallActions

    var body: some View {
        VStack(spacing: 10) {
            TilesView(peers: peers, me: me)
                .overlay(alignment: .topLeading) {
                    KinIndicator(on: kinOn, pausedBy: pausedBy, myPerson: myPerson).padding(12)
                }
                .padding(.horizontal, 12)
            CaptionBar(caption: world.caption, status: world.status, voiceOn: voiceOn) { actions.voice(!voiceOn) }
                .padding(.horizontal, 16)
            if !world.rail.isEmpty { CardRail(cards: world.rail, onAction: actions.card) }
            TypeBar(onSend: actions.send).padding(.horizontal, 16)
            ErrorText(message: error).padding(.horizontal, 16)
            ControlBar(kinOn: kinOn, micOn: micOn, cameraOn: cameraOn, invite: invite, actions: actions)
                .padding(.horizontal, 16)
        }
        .padding(.bottom, 8)
        .background(Theme.background)
    }
}

/// Quiet, persistent: everyone sees KIN is on, and who paused it when it is off.
struct KinIndicator: View {
    let on: Bool
    let pausedBy: PausedBy?
    let myPerson: String

    var text: String {
        if on { return "KIN is on" }
        guard let pausedBy else { return "KIN is paused" }
        return pausedBy.person == myPerson ? "You paused KIN" : "KIN paused by \(pausedBy.name)"
    }

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(on ? Theme.success : Theme.warning).frame(width: 8, height: 8)
            Text(text).font(.caption.weight(.semibold))
        }
        .padding(.horizontal, 10).padding(.vertical, 5)
        .background(.black.opacity(0.55), in: Capsule())
        .accessibilityElement(children: .combine)
    }
}

/// The other person's words in my language, large, with the voice toggle beside it (captions are the default).
struct CaptionBar: View {
    let caption: Caption?
    let status: String?
    let voiceOn: Bool
    let onVoice: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                if let status { Text(status).font(Theme.cardMetaFont).foregroundStyle(Theme.warning) }
                if let caption {
                    Text(caption.speaker).font(Theme.captionSpeakerFont).foregroundStyle(Theme.secondaryText)
                    Text(caption.text)
                        .font(Theme.captionFont)
                        .foregroundStyle(caption.isPartial ? Theme.secondaryText : .white)
                        .lineLimit(3)
                        .truncationMode(.head)  // a growing line keeps its newest words
                } else if status == nil {
                    Text("Captions appear here").font(Theme.cardBodyFont).foregroundStyle(Theme.secondaryText)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 56, alignment: .topLeading)
            Button(action: onVoice) {
                Image(systemName: voiceOn ? "speaker.wave.2.fill" : "speaker.slash.fill")
                    .font(.body)
                    .frame(width: 40, height: 40)
                    .background(voiceOn ? AnyShapeStyle(Theme.primaryGradient) : AnyShapeStyle(Theme.field), in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(voiceOn ? "Translated voice on" : "Translated voice off")
        }
    }
}

/// Typed input: KIN treats it like speech (demo insurance when the mic or ASR fails).
struct TypeBar: View {
    let onSend: (String) -> Void
    @State private var text = ""

    var body: some View {
        HStack(spacing: 8) {
            TextField("Type to KIN", text: $text)
                .submitLabel(.send)
                .onSubmit(send)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(Theme.field, in: Capsule())
            if !text.trimmingCharacters(in: .whitespaces).isEmpty {
                Button(action: send) { Image(systemName: "arrow.up.circle.fill").font(.title) }
                    .tint(Theme.accent)
                    .accessibilityLabel("Send")
            }
        }
    }

    private func send() {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        onSend(t)
        text = ""
    }
}

struct ControlBar: View {
    let kinOn: Bool
    let micOn: Bool
    let cameraOn: Bool
    let invite: URL?
    let actions: CallActions

    var body: some View {
        HStack(spacing: 12) {
            Button { actions.pause(kinOn) } label: {
                Label(kinOn ? "Pause KIN" : "Resume KIN", systemImage: kinOn ? "pause.fill" : "play.fill")
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, 14)
                    .frame(height: Theme.controlSize)
                    .background(Theme.field, in: Capsule())
            }
            Spacer(minLength: 0)
            if let invite { ShareLink(item: invite) { round("square.and.arrow.up", Theme.field) }.accessibilityLabel("Share invite") }
            Button { actions.mic(!micOn) } label: { round(micOn ? "mic.fill" : "mic.slash.fill", Theme.field) }
                .accessibilityLabel(micOn ? "Mute" : "Unmute")
            Button { actions.camera(!cameraOn) } label: { round(cameraOn ? "video.fill" : "video.slash.fill", Theme.field) }
                .accessibilityLabel(cameraOn ? "Camera off" : "Camera on")
            Button(action: actions.hangUp) { round("phone.down.fill", Theme.error) }
                .accessibilityLabel("End call")
        }
        .buttonStyle(.plain)
        .foregroundStyle(.white)
    }

    private func round(_ symbol: String, _ color: Color) -> some View {
        Image(systemName: symbol)
            .font(.title3)
            .frame(width: Theme.controlSize, height: Theme.controlSize)
            .background(color, in: Circle())
    }
}

#if DEBUG
/// `-demoCallScreen`: the 1:1 Arjun-Mei call from docs/collab/STORIES.md, without networking, for screenshots.
@MainActor
enum CallDemo {
    static var isRequested: Bool { ProcessInfo.processInfo.arguments.contains("-demoCallScreen") }

    static let messages: [String] = [
        #"{"type":"joined","call_id":1,"identity":"p3","person":"p_arjun_3","name":"Arjun","lang":"en","participants":[{"identity":"p5","person":"p_mei_5","name":"Mei","lang":"zh"}],"kin":{"on":true,"paused_by":null}}"#,
        #"{"type":"glance","speaker":"p5","items":[{"key":"story:3","kind":"storyline","title":"Mei's job search","storyline_id":3,"states":[{"label":"applied","at":"2026-09-02","known":true},{"label":"second round","at":"2026-10-10","known":false}]}]}"#,
        #"{"type":"glance","speaker":"p5","items":[{"key":"bridge:42","kind":"bridge","title":"You haven't told Mei","body":"you started bouldering","target":"p_mei_5","private":true}]}"#,
        #"{"type":"glance","speaker":"p5","items":[{"key":"who:p_lin_17","kind":"who","title":"Lin","native":"林","body":"Mei's friend from the Fudan climbing wall. She mentioned her Sept 14.","node_id":"p_lin_17","gap":"reminder"}]}"#,
        #"{"type":"transcript","call_id":1,"utterance_id":91,"speaker":"p_mei_5","speaker_identity":"p5","src_text":"我和林终于去了莫干山","src_lang":"zh","target_lang":"en","translation":"Lin and I finally did the Moganshan trip.","grounded_spans":[{"source":"林","rendered":"Mei's friend Lin","node_id":"p_lin_17"}]}"#,
    ]

    static func state(now: Date = .now) -> WorldState {
        messages.reduce(WorldState()) { reduce($0, KinWorldMsg.decode(Data($1.utf8)), me: "p3", now: now) }
    }

    static func view() -> CallScreen {
        CallScreen(world: state(), peers: [Tile(id: "p5", name: "Mei", track: nil)],
                   me: Tile(id: "p3", name: "Arjun", track: nil), myPerson: "p_arjun_3",
                   kinOn: true, pausedBy: nil, micOn: true, cameraOn: true, voiceOn: false,
                   invite: nil, error: nil, actions: CallActions())
    }
}
#endif
