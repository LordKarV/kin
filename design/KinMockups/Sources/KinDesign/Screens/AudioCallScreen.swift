import SwiftUI

/// Audio-only call. With no video, the conversation itself is the main surface: recent lines read like a transcript,
/// and cards sit inline under the line that triggered them (left for their world, right for your private chip).
public struct AudioCallScreen: View {
    public enum Item: Identifiable {
        case earlier(Caption), line(Caption, highlights: [String]), card(CallScreen.Slot), bridge(GlanceItem)
        public var id: String {
            switch self {
            case .earlier(let c): return "e\(c.id)"
            case .line(let c, _): return "l\(c.id)"
            case .card(let s): if case .gap(let i) = s { return i.key }; return "card"
            case .bridge(let i): return i.key
            }
        }
    }
    public struct Model {
        public var name: String, initial: String, hue: Double, place: String, localTime: String, duration: String
        public var route: (from: String, to: String)?
        public var voiceOn = false
        public var items: [Item]
        public var partial: String?
    }
    let m: Model
    public init(_ m: Model) { self.m = m }

    public var body: some View {
        ZStack {
            LinearGradient(colors: [Color(hex: 0x24303C), Color(hex: 0x18191A)], startPoint: .top, endPoint: .center).ignoresSafeArea()
            VStack(spacing: 0) {
                HStack { KinIndicator(.on); Spacer() }.padding(.horizontal, Space.gutter)
                VStack(spacing: 6) {
                    Avatar(m.initial, hue: m.hue, size: 84)
                    Text(m.name).font(KinFont.title).foregroundStyle(K.Call.text)
                    Text("\(m.duration)  ·  \(m.localTime) in \(m.place)").font(KinFont.subhead).foregroundStyle(K.Call.text2)
                }
                .padding(.top, 8)
                Spacer(minLength: 16)
                VStack(alignment: .leading, spacing: 12) {
                    if let route = m.route {
                        HStack {
                            RouteLabel(route)
                            Spacer()
                            HStack(spacing: 5) { Image(systemName: m.voiceOn ? "speaker.wave.2.fill" : "speaker.slash.fill"); Text(m.voiceOn ? "Voice on" : "Voice off") }
                                .font(KinFont.captionEmph).foregroundStyle(m.voiceOn ? Color.white : K.Call.text2)
                                .padding(.horizontal, 10).frame(height: 28)
                                .background(m.voiceOn ? K.Call.mine : Color.white.opacity(0.14), in: Capsule())
                        }
                    }
                    ForEach(m.items) { item in
                        switch item {
                        case .earlier(let c):
                            Text(c.readable).font(KinFont.callout).foregroundStyle(K.Call.text3).lineLimit(2)
                        case .line(let c, let h):
                            VStack(alignment: .leading, spacing: 3) {
                                if c.translation != nil { Text(c.original).font(KinFont.captionOriginal).foregroundStyle(K.Call.text3) }
                                Text(LiveCaptions.highlighted(c.readable, h)).font(KinFont.captionLine).foregroundStyle(K.Call.text)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        case .card(let s):
                            switch s {
                            case .gap(let i): GapCard(i)
                            case .meaning(let c): MeaningCard(c)
                            case .story(let i): StorylineCard(i)
                            case .ask(let i): AskCard(i, speakerName: m.name)
                            case .tappedGap(let i): GapCard(i, viaTap: true)
                            case .tappedAsk(let i): AskCard(i, speakerName: m.name, viaTap: true)
                            }
                        case .bridge(let i): HStack { Spacer(minLength: 48); BridgeChip(i) }
                        }
                    }
                    if let p = m.partial {
                        HStack(spacing: 6) { TypingDots(); Text(p).font(KinFont.callout).foregroundStyle(K.Call.text2) }
                    }
                }
                .padding(.horizontal, Space.gutter)
                CallControls(video: false).padding(.top, 22)
            }
            .padding(.top, Device.topInset + 4)
            .padding(.bottom, Device.bottomInset + 10)
        }
        .environment(\.colorScheme, .dark)
    }

    public static var demo: Model {
        Model(name: "Mei", initial: "美", hue: Cast.mei.hue, place: "Shanghai", localTime: "11:04 PM", duration: "14:22",
              route: ("Mandarin", "English"),
              items: [.earlier(Caption(Sample.meiHello)), .line(Caption(Sample.meiLin), highlights: ["Lin"]), .card(.gap(Sample.linReminder)), .bridge(Sample.boulderBridge)],
              partial: "上周末我们")
    }
}

struct AudioCallScreen_Previews: PreviewProvider {
    static var previews: some View { PhoneChrome(dark: true) { AudioCallScreen(AudioCallScreen.demo) } }
}
