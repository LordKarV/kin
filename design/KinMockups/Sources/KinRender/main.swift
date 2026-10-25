import SwiftUI
import AppKit
import KinDesign

// Renders every screen state to design/screens/*.png at iPhone 16 Pro resolution (393x852 pt at 2x), plus a contact
// sheet. This Mac has no Xcode/iOS SDK, so screenshots come from the same SwiftUI views rendered by ImageRenderer.

@MainActor func png<V: View>(_ v: V, _ path: String, scale: CGFloat = 2) -> CGImage? {
    let r = ImageRenderer(content: v)
    r.scale = scale
    guard let cg = r.cgImage else { print("FAILED \(path)"); return nil }
    try! NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: path))
    return cg
}

if CommandLine.arguments.dropFirst().first == "--brand" {
    MainActor.assumeIsolated { renderBrand(CommandLine.arguments.dropFirst(2).first ?? "brand") }
    exit(0)
}

let out = CommandLine.arguments.dropFirst().first ?? "screens"
try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)

MainActor.assumeIsolated {
    var shots: [(String, AnyView)] = []
    func call(_ name: String, _ m: CallScreen.Model, strings: KinStrings = .en) {
        shots.append((name, AnyView(PhoneChrome(dark: true) { CallScreen(m) }.environment(\.kinStrings, strings))))
    }
    for (name, view) in Screens.all { shots.append((name, view)) }
    call("call-01-quiet", CallStates.quiet)
    call("call-02-speaking", CallStates.speaking)
    call("call-03-who-reminder", CallStates.linCard)
    call("call-04-who-and-bridge", CallStates.linAndBridge)
    call("call-05-storyline", CallStates.storyline)
    call("call-06-meaning", CallStates.paattiMeaning)
    call("call-07-ask", CallStates.paattiAsk)
    call("call-08-term", CallStates.paattiTerm)
    call("call-09-same-language", CallStates.priyaSameLanguage)
    call("call-10-voice-on", CallStates.voiceOn)
    call("call-11-paused", CallStates.paused)
    call("call-12-poor-connection", CallStates.poorConnection)
    call("call-13-peer-without-kin", CallStates.peerWithoutKin)
    call("call-14-first-call", CallStates.firstCall)
    shots.append(("call-15-paatti-view-tamil", AnyView(PhoneChrome(dark: true) { CallScreen(PaattiView.model) }.environment(\.kinStrings, .ta))))
    shots.append(("call-16-audio", AnyView(PhoneChrome(dark: true) { AudioCallScreen(AudioCallScreen.demo) })))
    shots.append(("call-17-waiting-invite", AnyView(PhoneChrome(dark: true) { WaitingScreen(name: "Mei") })))
    shots.append(("call-18-mei-view-chinese", AnyView(PhoneChrome(dark: true) { CallScreen(CallStates.meiView) }.environment(\.kinStrings, .zh))))
    call("call-19-next-day-silence", CallStates.nextDay)
    call("call-20-two-ravis", CallStates.paattiTwoRavis)
    call("call-21-paatti-hike-bridge", CallStates.paattiHikeBridge)
    call("call-22-paused-by-me", CallStates.pausedByMe)

    let only = Set(CommandLine.arguments.dropFirst(2))
    var images: [(String, CGImage)] = []
    for (name, view) in shots where only.isEmpty || only.contains(where: { name.hasPrefix($0) }) {
        if let cg = png(view, "\(out)/\(name).png") { images.append((name, cg)); print("wrote \(name)") }
    }
    // contact sheet (1x thumbnails, 4 per row)
    if only.isEmpty {
        let cols = 4, tw: CGFloat = 393, th: CGFloat = 852, pad: CGFloat = 40, label: CGFloat = 44
        let rows = Int(ceil(Double(images.count) / Double(cols)))
        let sheet = ZStack(alignment: .topLeading) {
            Color(hex: 0xE4E6EB)
            ForEach(Array(images.enumerated()), id: \.offset) { i, item in
                VStack(alignment: .leading, spacing: 8) {
                    Image(decorative: item.1, scale: 2).resizable().frame(width: tw, height: th)
                        .clipShape(RoundedRectangle(cornerRadius: 44, style: .continuous))
                        .shadow(color: .black.opacity(0.18), radius: 14, y: 6)
                    Text(item.0).font(.system(size: 20, weight: .semibold, design: .monospaced)).foregroundStyle(Color(hex: 0x65676B))
                }
                .offset(x: pad + CGFloat(i % cols) * (tw + pad), y: pad + CGFloat(i / cols) * (th + pad + label))
            }
        }
        .frame(width: pad + CGFloat(cols) * (tw + pad), height: pad + CGFloat(rows) * (th + pad + label))
        _ = png(sheet, "\(out)/_contact-sheet.png", scale: 1)
        print("wrote _contact-sheet (\(images.count) screens)")
    }
}
