import Foundation

/// One CMDeviceMotion reading, reduced to what the twist needs: `rate` is rotationRate.y (rad/s, about the phone's
/// long axis in portrait) and `accel` is the magnitude of userAcceleration (g, gravity already removed).
struct TwistSample: Equatable {
    let t: TimeInterval
    let rate: Double
    let accel: Double
}

/// Double twist of the wrist (on-demand context): two opposite-sign rotation
/// spikes about the long axis within `window`, with no jolt of linear acceleration nearby, at most once per `debounce`.
/// Pure value type so tests can feed synthetic ~60 Hz sequences.
///
/// Known limit: thresholds are first guesses from a wrist flick (5-10 rad/s, under ~0.5 g); calibrate on a real
/// phone by logging `TwistSample`s during a call. Raise `spikeRate` if it fires while talking with your hands,
/// lower it if a deliberate twist is missed; raise `joltG` if twists themselves trip the jolt gate.
/// One out-and-back flick is two opposite spikes, so it fires. If that false-triggers while
/// talking with your hands, require 3 alternating spikes: make `pending` (first t, last sign, count) and fire at 3.
/// The fire lands `joltHold` after the second spike so the thump of setting the phone down can still cancel it.
struct TwistDetector {
    static let spikeRate = 4.0       // rad/s about the long axis
    static let window: TimeInterval = 0.6
    static let joltG = 0.9           // userAcceleration magnitude that means walking, a bump or setting the phone down
    static let joltHold: TimeInterval = 0.25  // a spike this close after a jolt is not a twist
    static let debounce: TimeInterval = 2.0

    private var current = 0          // sign of the spike in progress, 0 below the threshold
    private var pending: (t: TimeInterval, sign: Int)?
    private var lastJolt = -TimeInterval.infinity
    private var lastFire = -TimeInterval.infinity
    private var confirmAt: TimeInterval?  // second spike seen; fires once `joltHold` passes without a jolt

    /// Feeds one sample; true exactly when a double twist is confirmed (`joltHold` after its second spike).
    mutating func feed(_ s: TwistSample) -> Bool {
        let sign = s.rate > Self.spikeRate ? 1 : s.rate < -Self.spikeRate ? -1 : 0
        let isNewSpike = sign != 0 && sign != current
        current = sign
        if s.accel > Self.joltG {
            lastJolt = s.t
            pending = nil
            confirmAt = nil
            return false
        }
        if let c = confirmAt {
            guard s.t - c >= Self.joltHold else { return false }
            confirmAt = nil
            lastFire = c
            return true
        }
        guard isNewSpike, s.t - lastJolt > Self.joltHold else { return false }
        if let p = pending, p.sign == -sign, s.t - p.t <= Self.window, s.t - lastFire >= Self.debounce {
            confirmAt = s.t
            pending = nil
            return false
        }
        pending = (s.t, sign)
        return false
    }
}
