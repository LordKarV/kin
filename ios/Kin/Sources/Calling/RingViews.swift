import SwiftUI

/// The ring cover RootView shows over any screen while `model.ring` is not idle.
struct RingScreen: View {
    @ObservedObject var model: AppModel

    var body: some View {
        switch model.ring {
        case .idle:
            Color.black.ignoresSafeArea()
        case .outgoing(_, let peer, _, let delivered):
            OutgoingCallView(peer: peer, delivered: delivered, onCancel: { model.send(.cancel) },
                             onShareInvite: model.shareInviteInstead)
        case .incoming(_, let peer, let video):
            IncomingCallView(peer: peer, video: video, onAccept: { model.send(.answer) },
                             onDecline: { model.send(.decline) })
        case .unanswered(let peer, _, let message):
            OutgoingCallView(peer: peer, delivered: true, message: message, onCancel: { model.send(.dismiss) },
                             onShareInvite: model.shareInviteInstead)
        }
    }
}

/// "Calling Mei..." with Cancel; after a decline or no answer, the reason and "Share invite instead".
struct OutgoingCallView: View {
    let peer: RingPeer
    let delivered: Bool
    var message: String?
    let onCancel: () -> Void
    let onShareInvite: () -> Void

    var body: some View {
        RingLayout(peer: peer, title: message == nil ? "Calling \(peer.name)..." : peer.name,
                   status: message ?? (delivered ? "Ringing" : "\(peer.name)'s KIN app is not open right now")) {
            if message != nil || !delivered {
                Button("Share invite instead", action: onShareInvite)
                    .font(KinFont.headline).foregroundStyle(K.Call.text)
                    .padding(.horizontal, 20).padding(.vertical, 12).background(K.Call.control, in: Capsule())
            }
            if message == nil {
                RingButton(symbol: "phone.down.fill", label: "Cancel", tint: K.Call.end, action: onCancel)
            } else {
                RingButton(symbol: "xmark", label: "Close", tint: K.Call.control, action: onCancel)
            }
        }
    }
}

/// Someone is calling: name, video or audio, Accept and Decline.
struct IncomingCallView: View {
    let peer: RingPeer
    let video: Bool
    let onAccept: () -> Void
    let onDecline: () -> Void

    var body: some View {
        RingLayout(peer: peer, title: peer.name, status: video ? "KIN video call" : "KIN audio call") {
            HStack(spacing: 72) {
                RingButton(symbol: "phone.down.fill", label: "Decline", tint: K.Call.end, action: onDecline)
                RingButton(symbol: video ? "video.fill" : "phone.fill", label: "Accept", tint: K.Call.on, action: onAccept)
            }
        }
    }
}

private struct RingLayout<Controls: View>: View {
    let peer: RingPeer
    let title: String
    let status: String
    @ViewBuilder let controls: () -> Controls

    var body: some View {
        VStack(spacing: 14) {
            Spacer()
            Avatar(text: Avatar.initial(name: peer.name), size: 120, hue: Avatar.hue(for: peer.slug))
            Text(title).font(KinFont.title).foregroundStyle(K.Call.text).multilineTextAlignment(.center)
            Text(status).font(KinFont.subhead).foregroundStyle(K.Call.text2).multilineTextAlignment(.center)
            Spacer()
            VStack(spacing: 28, content: controls)
        }
        .padding(.horizontal, Space.gutter).padding(.bottom, 48)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(LinearGradient(colors: [Color(hue: Avatar.hue(for: peer.slug), saturation: 0.35, brightness: 0.28),
                                            .black], startPoint: .top, endPoint: .bottom).ignoresSafeArea())
    }
}

private struct RingButton: View {
    let symbol: String
    let label: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: symbol).font(.system(size: 28, weight: .semibold)).foregroundStyle(.white)
                    .frame(width: 72, height: 72).background(tint, in: Circle())
                Text(label).font(KinFont.footnote).foregroundStyle(K.Call.text2)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}
