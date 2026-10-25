import SwiftUI

/// "KIN is on" indicator. Both people always see it; the pause control lives inside it so pausing is one tap and
/// never hidden in a menu. Color is never the only signal: the state is also written out.
public struct KinIndicator: View {
    public enum State: Equatable { case on, pausedByMe, pausedBy(String), learning }
    let state: State
    let onTogglePause: () -> Void
    public init(_ state: State, onTogglePause: @escaping () -> Void = {}) { self.state = state; self.onTogglePause = onTogglePause }

    public var body: some View {
        HStack(spacing: 0) {
            HStack(spacing: 7) {
                switch state {
                case .on, .learning:
                    Circle().fill(Color(hex: 0x31A24C)).frame(width: 8, height: 8)
                    Text(state == .learning ? "KIN on · learning" : "KIN on")
                case .pausedByMe:
                    Image(systemName: "pause.fill").font(.system(size: 10, weight: .bold))
                    Text("KIN paused")
                case .pausedBy(let name):
                    Image(systemName: "pause.fill").font(.system(size: 10, weight: .bold))
                    Text("Paused by \(name)")
                }
            }
            .padding(.leading, 12).padding(.trailing, 10)
            Rectangle().fill(Color.white.opacity(0.22)).frame(width: 1, height: 16)
            Button(action: onTogglePause) {
                Group {
                    switch state {
                    case .on, .learning: Image(systemName: "pause.fill")
                    case .pausedByMe, .pausedBy: Text("Resume").font(.system(size: 13, weight: .semibold))
                    }
                }
                .font(.system(size: 11, weight: .bold))
                .padding(.horizontal, 11)
                .frame(minHeight: 32)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(state == .on || state == .learning ? "Pause KIN for this call" : "Resume KIN")
        }
        .font(.system(size: 13, weight: .semibold))
        .foregroundStyle(.white)
        .frame(height: 32)
        .background(Color.black.opacity(0.42), in: Capsule())
        .overlay(Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1))
        .contentShape(Rectangle().inset(by: -6))
    }
}

public struct CallControls: View {
    public var muted = false
    public var cameraOn = true
    public var video = true
    public init(muted: Bool = false, cameraOn: Bool = true, video: Bool = true) { self.muted = muted; self.cameraOn = cameraOn; self.video = video }

    public var body: some View {
        HStack(spacing: 0) {
            if video {
                control(cameraOn ? "video.fill" : "video.slash.fill", on: !cameraOn, label: cameraOn ? "Turn camera off" : "Turn camera on")
                Spacer(minLength: 0)
                control("arrow.triangle.2.circlepath.camera.fill", on: false, label: "Flip camera")
                Spacer(minLength: 0)
            } else {
                control("video.fill", on: false, label: "Switch to video")
                Spacer(minLength: 0)
            }
            control(muted ? "mic.slash.fill" : "mic.fill", on: muted, label: muted ? "Unmute" : "Mute")
            Spacer(minLength: 0)
            control("speaker.wave.2.fill", on: false, label: "Audio output")
            Spacer(minLength: 0)
            Button {} label: {
                Image(systemName: "phone.down.fill").font(.system(size: 22, weight: .semibold)).foregroundStyle(.white)
                    .frame(width: 60, height: 60).background(K.Call.end, in: Circle())
            }
            .buttonStyle(.plain).accessibilityLabel("End call")
        }
        .padding(.horizontal, Space.l)
    }

    private func control(_ symbol: String, on: Bool, label: String) -> some View {
        Button {} label: {
            Image(systemName: symbol).font(.system(size: 21, weight: .semibold))
                .foregroundStyle(on ? Color.black : Color.white)
                .frame(width: 60, height: 60)
                .background(on ? K.Call.controlOn : K.Call.control, in: Circle())
        }
        .buttonStyle(.plain).accessibilityLabel(label)
    }
}

/// Small self view. Top right, the "you" side of the screen (your private chips also align right).
public struct SelfView: View {
    let look: VideoPlaceholder.Look
    public init(_ look: VideoPlaceholder.Look) { self.look = look }
    public var body: some View {
        VideoPlaceholder(look).frame(width: 104, height: 150)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color.white.opacity(0.18), lineWidth: 1))
            .shadow(color: .black.opacity(0.35), radius: 12, y: 4)
            .accessibilityLabel("Your camera")
    }
}

/// A one-line banner for call problems (connection, the other side without KIN). Sits under the top bar.
public struct CallBanner: View {
    let symbol: String; let text: String; let tint: Color
    public init(_ symbol: String, _ text: String, tint: Color = .white) { self.symbol = symbol; self.text = text; self.tint = tint }
    public var body: some View {
        HStack(spacing: 8) {
            Image(systemName: symbol).foregroundStyle(tint)
            Text(text).foregroundStyle(.white).lineLimit(2).fixedSize(horizontal: false, vertical: true)
        }
        .font(KinFont.footnoteEmph)
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(Color.black.opacity(0.55), in: Capsule())
    }
}
