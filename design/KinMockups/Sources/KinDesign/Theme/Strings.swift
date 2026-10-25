import SwiftUI

/// The few chrome strings the call layer draws itself, in the listener's language. Captions and card bodies arrive
/// already localized from the server; this covers the labels around them. The real app uses String Catalogs.
public struct KinStrings: Sendable {
    public var newToYou = "New to you", reminder = "Mentioned before", voiceOn = "Voice on", voiceOff = "Voice off"
    public var onlyYou = "Only you see this", whatItMeans = "What it means", catchingUp = "Catching up"
    public var youAsked = "You asked"
    public static let en = KinStrings()
    public static let ta = KinStrings(newToYou: "உங்களுக்குப் புதியது", reminder: "முன்பு கேட்டது", voiceOn: "குரல் ஆன்",
                                      voiceOff: "குரல் ஆஃப்", onlyYou: "உங்களுக்கு மட்டும்", whatItMeans: "இதன் அர்த்தம்",
                                      catchingUp: "தொடர்ச்சி", youAsked: "நீங்கள் கேட்டது")
    public static let zh = KinStrings(newToYou: "第一次听说", reminder: "之前提过", voiceOn: "语音开", voiceOff: "语音关",
                                      onlyYou: "仅你可见", whatItMeans: "意思是", catchingUp: "近况", youAsked: "你问的")
}

private struct KinStringsKey: EnvironmentKey { static let defaultValue = KinStrings.en }
public extension EnvironmentValues {
    var kinStrings: KinStrings { get { self[KinStringsKey.self] } set { self[KinStringsKey.self] = newValue } }
}
