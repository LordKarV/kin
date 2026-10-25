import SwiftUI

// TODO(4B): placeholder call screen; task 4B replaces this file with captions, cards, pause and the voice toggle.
struct CallView: View {
    @ObservedObject var call: CallController
    let invite: URL?

    var body: some View {
        VStack(spacing: 12) {
            TilesView(peers: call.peers, me: call.selfTile)
            ErrorText(message: call.lastError)
            HStack(spacing: 12) {
                if let invite { ShareLink(item: invite) { Image(systemName: "square.and.arrow.up") } }
                Button { Task { await call.setMic(!call.micOn) } } label: { Image(systemName: call.micOn ? "mic.fill" : "mic.slash.fill") }
                Button { Task { await call.setCamera(!call.cameraOn) } } label: { Image(systemName: call.cameraOn ? "video.fill" : "video.slash.fill") }
                Button(role: .destructive) { Task { await call.hangUp() } } label: { Image(systemName: "phone.down.fill") }
            }
            .font(.title2)
            .padding(.bottom, 8)
        }
    }
}
