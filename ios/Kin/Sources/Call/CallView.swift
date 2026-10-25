import SwiftUI

/// The one call screen (docs/ARCHITECTURE.md 8, 9.1): same for everyone, no roles. Feeds `kin` messages through the
/// pure reducer and turns taps into CallController / REST calls. All drawing is in `CallScreen`, which takes values.
struct CallView: View {
    @ObservedObject var call: CallController
    let invite: URL?
    @State private var world = WorldState()
    @Environment(\.scenePhase) private var scenePhase

    /// The double twist listens only in a live call with KIN on and the app in front (Amendment 7).
    private var gestureArmed: Bool { call.isConnected && !call.isPaused && scenePhase == .active }

    var body: some View {
        CallScreen(
            world: world, peers: call.peers, me: call.selfTile, myPerson: call.join.person, myLang: call.join.lang,
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
                card: handle,
                explain: explain))
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
        .onChange(of: gestureArmed, initial: true) { _, armed in
            if armed { MotionService.shared.start(onTwist: askRecent) } else { MotionService.shared.stop() }
        }
        .onDisappear { MotionService.shared.stop() }
        #if DEBUG
        .onReceive(NotificationCenter.default.publisher(for: .kinDebugShake)) { _ in if gestureArmed { askRecent() } }
        #endif
    }

    /// Double twist: a light tap, then the card for what the last lines are about lands in the card slot with the
    /// same "You asked" tag as a caption tap. Nothing clear: a soft haptic and nothing on screen.
    private func askRecent() {
        MotionService.tapHaptic()
        guard let started = explainStarted(world, term: recentAsk) else { return }
        world = started
        Task {
            do {
                let items = try await call.explainRecent()
                if items.isEmpty { MotionService.nothingHaptic() }
                world = recentExplained(world, items: items, now: .now)
            } catch {
                world = recentFailed(world, message: error.localizedDescription)
            }
        }
    }

    /// Tap-to-explain: the answer lands in the card slot (or as an ask card). Private to me; nothing is broadcast.
    private func explain(_ term: String) {
        guard let started = explainStarted(world, term: term) else { return }
        world = started
        let utterance = world.caption?.utteranceId
        Task {
            do {
                let items = try await call.explain(term, utteranceId: utterance)
                world = explained(world, term: term, items: items, now: .now)
            } catch {
                world = explainFailed(world, term: term, message: error.localizedDescription)
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
                do { _ = try await call.place(body) } catch {
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
    var explain: (String) -> Void = { _ in }
}

/// Layout rules from docs/collab/design-notes.md: the call fills the screen; left is them, right is you; help lives
/// in the lower third (one card about their world plus at most one bridge, then captions, then controls); the
/// "KIN on" pill with its pause button is always top left. Paused is one short note, never a separate screen.
struct CallScreen: View {
    let world: WorldState
    let peers: [Tile]
    let me: Tile?
    let myPerson: String
    let myLang: String
    let kinOn: Bool
    let pausedBy: PausedBy?
    let micOn: Bool
    let cameraOn: Bool
    let voiceOn: Bool
    let invite: URL?
    let error: String?
    let actions: CallActions
    @State private var typing = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            remote.ignoresSafeArea()
            LinearGradient(stops: [.init(color: .black.opacity(0.35), location: 0), .init(color: .clear, location: 0.16),
                                   .init(color: .clear, location: 0.45), .init(color: K.Call.scrimBottom, location: 1)],
                           startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea().allowsHitTesting(false)
            VStack(spacing: 0) {
                topBar
                Spacer(minLength: 0)
                bottom
            }
            .padding(.top, 4).padding(.bottom, 6)
        }
        .environment(\.colorScheme, .dark)
        .environment(\.openURL, OpenURLAction { url in
            guard let term = ExplainLink.term(url) else { return .systemAction }
            actions.explain(term)
            return .handled
        })
    }

    @ViewBuilder private var remote: some View {
        if peers.count == 1 { RemoteView(tile: peers[0]) } else { TilesView(peers: peers, me: me, pip: false) }
    }

    private var topBar: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 8) {
                KinIndicator(on: kinOn, pausedBy: pausedBy, myPerson: myPerson) { actions.pause(kinOn) }
                if let status = world.status { CallBanner(symbol: "wifi.exclamationmark", text: status, tint: Theme.warning) }
                if let error { CallBanner(symbol: "exclamationmark.triangle.fill", text: error, tint: Theme.warning) }
            }
            Spacer(minLength: 12)
            if let me, !peers.isEmpty { SelfPip(tile: me) }
        }
        .padding(.horizontal, Space.gutter)
    }

    private var bottom: some View {
        let shown = slots(world.rail)
        let speaker = world.caption?.speaker ?? world.partial?.speaker ?? peers.first?.name ?? ""
        return VStack(spacing: 10) {
            if kinOn {
                if let bridge = shown.bridge {
                    HStack { Spacer(minLength: 48); CardView(card: bridge, speakerName: speaker, onAction: actions.card) }
                        .padding(.top, 9).id(bridge.key)
                        .transition(KinMotion.cardTransition(reduceMotion: reduceMotion))
                }
                if let card = shown.card {
                    CardView(card: card, speakerName: speaker, onAction: actions.card).id(card.key)
                        .transition(KinMotion.cardTransition(reduceMotion: reduceMotion))
                }
                captions(speaker: speaker, card: shown.card).padding(.top, 4)
            } else {
                PausedNote()
            }
            if typing { TypeBar(onSend: actions.send) }
            CallControls(micOn: micOn, cameraOn: cameraOn, typing: typing, invite: invite, actions: actions,
                         onType: { typing.toggle() })
                .padding(.top, 12)
        }
        .padding(.horizontal, Space.gutter)
        .animation(reduceMotion ? KinMotion.fade : KinMotion.card, value: [shown.card?.key, shown.bridge?.key])
    }

    private func captions(speaker: String, card: RailCard?) -> some View {
        let caption = world.caption
        let route = caption.flatMap { c -> (from: String, to: String)? in
            guard c.original != nil, let from = c.lang, let to = c.targetLang else { return nil }
            return (languageName(from), languageName(to))
        }
        let text = caption?.text ?? ""
        let hot = triggerTerms(card).filter { !termRanges(of: $0, in: text).isEmpty }
        let cross = world.participants.contains { $0.person != myPerson && $0.lang != myLang }
        return LiveCaptions(speakerName: speaker, route: route, crossLanguage: cross,
                            previous: card == nil ? world.previous : nil,
                            current: caption, partial: world.partial,
                            tappable: tappableTerms(in: text, known: world.known),
                            tappableOriginal: caption?.original.map { tappableTerms(in: $0, known: world.known) } ?? [],
                            highlights: hot,
                            hint: world.hint, voiceOn: voiceOn) { actions.voice(!voiceOn) }
    }
}

/// The other person, full screen: video when there is a track, else their avatar on a dark wash.
struct RemoteView: View {
    let tile: Tile

    var body: some View {
        if tile.track != nil {
            TileView(tile: tile, showName: false).clipShape(Rectangle())
        } else {
            ZStack {
                LinearGradient(colors: [Color(hex: 0x3B4A5A), Color(hex: 0x1D252E)], startPoint: .topTrailing, endPoint: .bottomLeading)
                VStack {
                    Avatar(text: Avatar.initial(name: tile.name), size: 132)
                    Spacer().frame(height: 220)  // keep the face in the upper middle, above the help area
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(tile.name), camera off")
        }
    }
}

/// "KIN on" pill: both people always see it, and its pause button is one tap (Amendment 6). State is written out,
/// so color is never the only signal.
struct KinIndicator: View {
    let on: Bool
    let pausedBy: PausedBy?
    let myPerson: String
    var onToggle: () -> Void = {}

    var text: String {
        if on { return "KIN on" }
        guard let pausedBy else { return "KIN paused" }
        return pausedBy.person == myPerson ? "You paused KIN" : "Paused by \(pausedBy.name)"
    }

    var body: some View {
        HStack(spacing: 0) {
            HStack(spacing: 7) {
                if on { Circle().fill(K.Call.on).frame(width: 8, height: 8) } else {
                    Image(systemName: "pause.fill").font(.caption2.weight(.bold))
                }
                Text(text)
            }
            .padding(.leading, 12).padding(.trailing, 10)
            Rectangle().fill(Color.white.opacity(0.22)).frame(width: 1, height: 16)
            Button(action: onToggle) {
                Group {
                    if on { Image(systemName: "pause.fill") } else { Text("Resume").font(KinFont.footnoteEmph) }
                }
                .font(.caption.weight(.bold))
                .padding(.horizontal, 11)
                .frame(minWidth: 44, minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(on ? "Pause KIN for this call" : "Resume KIN")
        }
        .font(KinFont.footnoteEmph)
        .foregroundStyle(.white)
        .frame(height: 32)
        .background(Color.black.opacity(0.42), in: Capsule())
        .overlay(Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1))
    }
}

/// One short line under the pill for call problems (connection, pipeline errors). Never a modal.
struct CallBanner: View {
    let symbol: String
    let text: String
    let tint: Color

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: symbol).foregroundStyle(tint)
            Text(text).foregroundStyle(.white).lineLimit(2).fixedSize(horizontal: false, vertical: true)
        }
        .font(KinFont.footnoteEmph)
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(Color.black.opacity(0.55), in: Capsule())
    }
}

struct PausedNote: View {
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "pause.circle.fill").font(.title2).foregroundStyle(K.Call.text2)
            VStack(alignment: .leading, spacing: 2) {
                Text("KIN is paused for this call").font(KinFont.headline).foregroundStyle(K.Call.text)
                Text("No captions or cards, and nothing is transcribed or remembered until someone resumes.")
                    .font(KinFont.subhead).foregroundStyle(K.Call.text2).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 4)
        .accessibilityElement(children: .combine)
    }
}

/// Typed input: KIN treats it like speech (a fallback when the mic or speech recognition fails). Behind the keyboard control.
struct TypeBar: View {
    let onSend: (String) -> Void
    @State private var text = ""

    var body: some View {
        HStack(spacing: 8) {
            TextField("Type to KIN", text: $text)
                .submitLabel(.send)
                .onSubmit(send)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(K.Call.control, in: Capsule())
            if !text.trimmingCharacters(in: .whitespaces).isEmpty {
                Button(action: send) { Image(systemName: "arrow.up.circle.fill").font(.title) }
                    .tint(K.Call.highlight)
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

/// Round 60 pt controls; a control that is "off" (camera off, muted) turns white so the state reads at a glance.
struct CallControls: View {
    let micOn: Bool
    let cameraOn: Bool
    let typing: Bool
    let invite: URL?
    let actions: CallActions
    let onType: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            control(cameraOn ? "video.fill" : "video.slash.fill", lit: !cameraOn,
                    label: cameraOn ? "Turn camera off" : "Turn camera on") { actions.camera(!cameraOn) }
            Spacer(minLength: 0)
            control(micOn ? "mic.fill" : "mic.slash.fill", lit: !micOn, label: micOn ? "Mute" : "Unmute") { actions.mic(!micOn) }
            Spacer(minLength: 0)
            control("keyboard", lit: typing, label: typing ? "Hide typing" : "Type to KIN", action: onType)
            Spacer(minLength: 0)
            if let invite {
                ShareLink(item: invite) { circle("square.and.arrow.up", lit: false) }.accessibilityLabel("Share invite")
                Spacer(minLength: 0)
            }
            Button(action: actions.hangUp) {
                Image(systemName: "phone.down.fill").font(.title2.weight(.semibold)).foregroundStyle(.white)
                    .frame(width: 60, height: 60).background(K.Call.end, in: Circle())
            }
            .buttonStyle(.plain).accessibilityLabel("End call")
        }
        .padding(.horizontal, 4)
    }

    private func control(_ symbol: String, lit: Bool, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { circle(symbol, lit: lit) }.buttonStyle(.plain).accessibilityLabel(label)
    }

    private func circle(_ symbol: String, lit: Bool) -> some View {
        Image(systemName: symbol).font(.title3.weight(.semibold))
            .foregroundStyle(lit ? Color.black : Color.white)
            .frame(width: 60, height: 60)
            .background(lit ? Color.white : K.Call.control, in: Circle())
    }
}
