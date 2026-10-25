import CoreMotion
import UIKit

/// Runs CMMotionManager's device motion through a TwistDetector while the call screen arms it (connected, KIN on,
/// app in the foreground). One shared instance: Apple asks for a single CMMotionManager per app. Raw device motion
/// needs no permission prompt; NSMotionUsageDescription covers CMPedometer and activity APIs, which KIN does not use.
@MainActor
final class MotionService {
    static let shared = MotionService()
    static let sampleRate: TimeInterval = 1.0 / 60

    private let manager = CMMotionManager()
    private var detector = TwistDetector()
    private var onTwist: (@MainActor () -> Void)?

    func start(onTwist: @escaping @MainActor () -> Void) {
        self.onTwist = onTwist
        guard manager.isDeviceMotionAvailable, !manager.isDeviceMotionActive else { return }  // simulator: unavailable
        detector = TwistDetector()
        manager.deviceMotionUpdateInterval = Self.sampleRate
        manager.startDeviceMotionUpdates(to: .main) { [weak self] motion, error in
            guard let self else { return }
            if let error { print("kin: device motion failed: \(error.localizedDescription)"); self.stop(); return }
            guard let motion else { return }
            let a = motion.userAcceleration
            let sample = TwistSample(t: motion.timestamp, rate: motion.rotationRate.y,
                                     accel: (a.x * a.x + a.y * a.y + a.z * a.z).squareRoot())
            if self.detector.feed(sample) { self.onTwist?() }
        }
    }

    func stop() {
        onTwist = nil
        manager.stopDeviceMotionUpdates()
    }

    /// Light tap when a twist is heard; a soft notification when KIN found nothing to explain.
    static func tapHaptic() { UIImpactFeedbackGenerator(style: .light).impactOccurred() }
    static func nothingHaptic() { UINotificationFeedbackGenerator().notificationOccurred(.warning) }
}

#if DEBUG
extension Notification.Name {
    /// The simulator has no motion sensors; Device > Shake stands in for the double twist in debug builds.
    static let kinDebugShake = Notification.Name("kinDebugShake")
}

extension UIWindow {
    open override func motionEnded(_ motion: UIEvent.EventSubtype, with event: UIEvent?) {
        if motion == .motionShake { NotificationCenter.default.post(name: .kinDebugShake, object: nil) }
        super.motionEnded(motion, with: event)
    }
}
#endif
