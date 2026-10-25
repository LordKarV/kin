import SwiftUI

/// Named call states used by previews and the screenshot renderer.
public enum CallStates {
    static func mei() -> CallScreen.Model {
        var m = CallScreen.Model(remoteName: "Mei", remote: .mei); m.route = ("Mandarin", "English"); return m
    }
    static func paatti() -> CallScreen.Model {
        var m = CallScreen.Model(remoteName: "Paatti", remote: .paatti); m.route = ("Tamil", "English"); return m
    }

    /// The default: a call with captions and nothing else.
    public static var quiet: CallScreen.Model { var m = mei(); m.current = Caption(Sample.meiHello); return m }
    /// Mei is mid-sentence: the big line stays still; her live words show small underneath.
    public static var speaking: CallScreen.Model { var m = mei(); m.current = Caption(Sample.meiHello); m.partial = "我和林终于去莫干山"; return m }
    /// Story 1: the Lin reminder lands with the line that mentioned her.
    public static var linCard: CallScreen.Model {
        var m = mei(); m.previous = Caption(Sample.meiHello); m.current = Caption(Sample.meiLin); m.highlights = ["Lin"]
        m.slot = .gap(Sample.linReminder); return m
    }
    /// Story 1 + 2: plus the private bouldering bridge, on your side.
    public static var linAndBridge: CallScreen.Model { var m = linCard; m.bridge = Sample.boulderBridge; return m }
    /// Story 3
    public static var storyline: CallScreen.Model {
        var m = mei(); m.previous = Caption(Sample.meiLin); m.current = Caption(Sample.meiByteDance); m.highlights = ["ByteDance"]
        m.slot = .story(Sample.jobStory); return m
    }
    /// Story 6 + 7: the right Ravi in the caption, and what "you've gotten thin" really means.
    public static var paattiMeaning: CallScreen.Model {
        var m = paatti(); m.previous = Caption(Sample.paattiRavi); m.current = Caption(Sample.paattiThin)
        m.slot = .meaning(Sample.thinMeaning); return m
    }
    public static var paattiAsk: CallScreen.Model {
        var m = paatti(); m.current = Caption(Sample.paattiRaviMama); m.highlights = ["Ravi mama"]; m.slot = .ask(Sample.raviAsk); return m
    }
    public static var paattiTerm: CallScreen.Model {
        var m = paatti(); m.previous = Caption(Sample.paattiRavi); m.current = Caption(Sample.paattiMurukku); m.highlights = ["murukku"]
        m.slot = .gap(Sample.murukku); return m
    }
    /// Same-language friends: no captions route, no voice toggle; cards still work.
    public static var priyaSameLanguage: CallScreen.Model {
        var m = CallScreen.Model(remoteName: "Priya", remote: .priya); m.current = Caption(Sample.priyaJess); m.highlights = ["Jess"]
        m.slot = .gap(Sample.jessNew); return m
    }
    public static var voiceOn: CallScreen.Model { var m = paattiMeaning; m.voiceOn = true; return m }
    public static var paused: CallScreen.Model { var m = mei(); m.kin = .pausedBy("Mei"); return m }
    public static var poorConnection: CallScreen.Model {
        var m = mei(); m.current = Caption(Sample.meiHello)
        m.banner = ("wifi", "The connection is a little slow, so captions may lag.", Color(hex: 0xF7B928)); return m
    }
    public static var peerWithoutKin: CallScreen.Model {
        var m = mei(); m.current = Caption(Sample.meiHello)
        m.banner = ("person.crop.circle.badge.questionmark", "Mei joined without KIN, so captions are just for you.", .white); return m
    }
    public static var firstCall: CallScreen.Model {
        var m = mei(); m.kin = .learning; m.current = Caption(Sample.meiHello)
        m.banner = ("hand.wave.fill", "Your first call with Mei. KIN gets to know who's who as you talk.", .white); return m
    }
}

public extension CallStates {
    /// Film shot 7, Mei's phone: Arjun's line as a Chinese caption, and no card (it is her own world).
    static var meiView: CallScreen.Model {
        var m = CallScreen.Model(remoteName: "Arjun", remote: .arjun); m.me = .mei; m.route = ("英语", "中文")
        m.previous = Caption(Sample.arjunHowLinForMei); m.current = Caption(Sample.arjunBoulderForMei); return m
    }
    /// Film shot 8: the same sentence the next day. Captions only; KIN stays quiet.
    static var nextDay: CallScreen.Model { var m = mei(); m.current = Caption(Sample.meiLin); return m }
    /// Film shot 10: the two Ravis, each named for who he is to Arjun.
    static var paattiTwoRavis: CallScreen.Model {
        var m = paatti(); m.previous = Caption(Sample.paattiRaviMamaGrounded); m.current = Caption(Sample.paattiRaviPeriyappa)
        m.highlights = ["Ravi periyappa"]; return m
    }
    /// Film shot 10: she asks about his friends, and his own news about Mei becomes a private chip.
    static var paattiHikeBridge: CallScreen.Model {
        var m = paatti(); m.previous = Caption(Sample.paattiRaviPeriyappa); m.current = Caption(Sample.paattiFriends)
        m.bridge = Sample.hikeBridge; return m
    }
    /// Film shot 12: you paused KIN yourself.
    static var pausedByMe: CallScreen.Model { var m = mei(); m.kin = .pausedByMe; return m }
}

/// Story 9 from Paatti's side: same app, her language. Arjun's line arrives as a Tamil caption, and a card explains
/// who Mei is to him, using only what Arjun himself has said about Mei.
public enum PaattiView {
    public static var model: CallScreen.Model {
        var m = CallScreen.Model(remoteName: "Arjun", remote: .arjun); m.me = .paatti
        m.route = ("ஆங்கிலம்", "தமிழ்")
        m.current = Caption(Sample.arjunHikeForPaatti); m.highlights = ["மெய்"]
        m.slot = .gap(Sample.meiForPaatti); return m
    }
}
