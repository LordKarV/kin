import AVFoundation
import os
import UIKit

/// Ringback while I call, ringtone plus haptics while I am called. iOS has no public API for the system ringtone, so
/// both are synthesized (no audio files to ship). The session goes to .playback so the ring is heard with the silent
/// switch on; LiveKit sets .playAndRecord itself when the call starts (AudioManager automatic configuration).
@MainActor
final class RingTone {
    enum Kind: Equatable {
        case ringback  // US ringback: 440 + 480 Hz, 2 s on, 4 s off
        case ringtone  // a double ring: 400 + 450 Hz, 0.4 s on, 0.2 s off, 0.4 s on, 2 s off
    }

    static let sampleRate: Double = 22_050
    private static let log = Logger(subsystem: "dev.kin.app", category: "ring")
    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private var playing: Kind?
    private var haptics: Task<Void, Never>?

    /// What should sound for this ring state.
    nonisolated static func kind(for ring: RingState) -> Kind? {
        switch ring {
        case .outgoing: return .ringback
        case .incoming: return .ringtone
        case .idle, .unanswered: return nil
        }
    }

    func update(_ ring: RingState) {
        let kind = Self.kind(for: ring)
        guard kind != playing else { return }
        stop()
        if let kind { play(kind) }
    }

    private func play(_ kind: Kind) {
        playing = kind
        if kind == .ringtone {
            haptics = Task {
                let tap = UINotificationFeedbackGenerator()
                while !Task.isCancelled {
                    tap.notificationOccurred(.warning)
                    try? await Task.sleep(for: .seconds(1.5))
                }
            }
        }
        guard let format = AVAudioFormat(standardFormatWithSampleRate: Self.sampleRate, channels: 1),
              let buffer = Self.buffer(kind, format: format) else { return }
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
            try AVAudioSession.sharedInstance().setActive(true)
            if player.engine == nil { engine.attach(player) }
            engine.connect(player, to: engine.mainMixerNode, format: format)
            try engine.start()
            player.scheduleBuffer(buffer, at: nil, options: .loops)
            player.play()
        } catch {
            Self.log.error("ring tone failed: \(error.localizedDescription)")  // haptics still ring
        }
    }

    func stop() {
        playing = nil
        haptics?.cancel()
        haptics = nil
        if engine.isRunning {
            player.stop()
            engine.stop()
        }
    }

    /// One loop of the pattern as (tone on?, seconds).
    nonisolated static func pattern(_ kind: Kind) -> (freqs: [Double], segments: [(on: Bool, seconds: Double)]) {
        switch kind {
        case .ringback: return ([440, 480], [(true, 2), (false, 4)])
        case .ringtone: return ([400, 450], [(true, 0.4), (false, 0.2), (true, 0.4), (false, 2)])
        }
    }

    private static func buffer(_ kind: Kind, format: AVAudioFormat) -> AVAudioPCMBuffer? {
        let (freqs, segments) = pattern(kind)
        let frames = segments.reduce(0) { $0 + Int($1.seconds * sampleRate) }
        guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)),
              let out = buf.floatChannelData?[0] else { return nil }
        buf.frameLength = AVAudioFrameCount(frames)
        var i = 0
        for seg in segments {
            for _ in 0..<Int(seg.seconds * sampleRate) {
                let t = Double(i) / sampleRate
                out[i] = seg.on ? Float(freqs.reduce(0) { $0 + 0.2 * sin(2 * .pi * $1 * t) }) : 0
                i += 1
            }
        }
        return buf
    }
}
