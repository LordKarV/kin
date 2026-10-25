import SwiftUI

/// The core screen: a one-to-one video call. By default it is just a call (plus captions when languages differ).
/// Help appears in the lower third, at most one card about their world and one private chip about yours.
public struct CallScreen: View {
    public enum Slot {
        case gap(GlanceItem), meaning(PragmaticsCard), story(GlanceItem), ask(GlanceItem)
        case tappedGap(GlanceItem), tappedAsk(GlanceItem)     // answers to tapping a word in the caption
    }
    public struct Model {
        public var remoteName: String
        public var remote: VideoPlaceholder.Look
        public var me: VideoPlaceholder.Look = .arjun
        public var route: (from: String, to: String)? = nil
        public var kin: KinIndicator.State = .on
        public var previous: Caption? = nil
        public var current: Caption? = nil
        public var partial: String? = nil
        public var highlights: [String] = []
        public var tappable: [String] = []
        public var pressed: String? = nil
        public var tip = false
        public var slot: Slot? = nil
        public var bridge: GlanceItem? = nil
        public var banner: (symbol: String, text: String, tint: Color)? = nil
        public var voiceOn = false
        public var muted = false
        public init(remoteName: String, remote: VideoPlaceholder.Look) { self.remoteName = remoteName; self.remote = remote }
    }
    let m: Model
    public init(_ m: Model) { self.m = m }

    var paused: Bool { if case .on = m.kin { return false }; if case .learning = m.kin { return false }; return true }

    public var body: some View {
        ZStack {
            VideoPlaceholder(m.remote).ignoresSafeArea()
            LinearGradient(stops: [.init(color: .black.opacity(0.35), location: 0), .init(color: .clear, location: 0.16),
                                   .init(color: .clear, location: 0.5), .init(color: K.Call.scrimBottom, location: 1)],
                           startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea().allowsHitTesting(false)
            VStack(spacing: 0) {
                topBar
                Spacer(minLength: 0)
                bottom
            }
            .padding(.top, Device.topInset + 4)
            .padding(.bottom, Device.bottomInset + 10)
        }
        .environment(\.colorScheme, .dark)
    }

    private var topBar: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 8) {
                KinIndicator(m.kin)
                if let b = m.banner { CallBanner(b.symbol, b.text, tint: b.tint) }
            }
            Spacer(minLength: 12)
            SelfView(m.me)
        }
        .padding(.horizontal, Space.gutter)
    }

    private var bottom: some View {
        VStack(spacing: 10) {
            if paused {
                pausedNote
            } else {
                if let bridge = m.bridge { HStack { Spacer(minLength: 48); BridgeChip(bridge) }.padding(.top, 9) }
                if let slot = m.slot { slotView(slot) }
                if m.tip { HStack { CaptionTip(); Spacer() } }
                LiveCaptions(speakerName: m.remoteName, route: m.route, previous: m.slot == nil ? m.previous : nil, current: m.current,
                             partial: m.partial, highlights: m.highlights, tappable: m.tappable, pressed: m.pressed, voiceOn: m.voiceOn)
                    .padding(.top, 4)
            }
            CallControls(muted: m.muted).padding(.top, 12)
        }
        .padding(.horizontal, Space.gutter)
    }

    @ViewBuilder private func slotView(_ slot: Slot) -> some View {
        switch slot {
        case .gap(let i): GapCard(i)
        case .meaning(let c): MeaningCard(c)
        case .story(let i): StorylineCard(i)
        case .ask(let i): AskCard(i, speakerName: m.remoteName)
        case .tappedGap(let i): GapCard(i, viaTap: true)
        case .tappedAsk(let i): AskCard(i, speakerName: m.remoteName, viaTap: true)
        }
    }

    /// Pause stays tiny: the pill says who paused and holds Resume; the caption area just says it is quiet.
    private var pausedNote: some View {
        HStack(spacing: 8) {
            Image(systemName: "cup.and.saucer.fill").font(.system(size: 14))
            Text("KIN is taking a break. Nothing is captioned or saved.")
        }
        .font(KinFont.subhead).foregroundStyle(K.Call.text2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 4)
    }
}

struct CallScreen_Previews: PreviewProvider {
    static var previews: some View {
        PhoneChrome(dark: true) { CallScreen(CallStates.linAndBridge) }
    }
}
