import Foundation

/// Demo data from docs/collab/STORIES.md, written as the exact wire JSON of ARCHITECTURE section 9.1 and decoded with
/// the real contracts. If the server shape changes, these stop decoding, which is the point.
public enum Sample {
    static func decode<T: Decodable>(_ json: String) -> T {
        do { return try JSONDecoder().decode(T.self, from: Data(json.utf8)) }
        catch { fatalError("sample does not match the contract: \(T.self): \(error)") }
    }

    // Story 1 and 2: Arjun and Mei, six weeks after she first mentioned Lin.
    public static let linReminder: GlanceItem = decode(#"""
    {"key":"who:p_lin_17","kind":"who","title":"Lin","native":"林","body":"Mei's friend from the Fudan climbing wall, first mentioned Sep 14","category":"person","node_id":"p_lin_17","gap":"reminder"}
    """#)
    public static let linNew: GlanceItem = decode(#"""
    {"key":"who:p_lin_17","kind":"who","title":"Lin","native":"林","body":"Mei's friend from the Fudan climbing wall","category":"person","node_id":"p_lin_17","gap":"new"}
    """#)
    public static let boulderBridge: GlanceItem = decode(#"""
    {"key":"bridge:41","kind":"bridge","title":"Mei hasn't heard yet","body":"you started bouldering","target":"p_mei_5","private":true}
    """#)
    // Story 3
    public static let jobStory: GlanceItem = decode(#"""
    {"key":"story:3","kind":"storyline","title":"Mei's job search","body":"applied (Sep) -> second round (Oct)","storyline_id":3,
     "states":[{"label":"applied","at":"2026-09-02","known":true},{"label":"second round","at":"2026-10-10","known":false}]}
    """#)
    // Story 6: first time KIN hears "Ravi mama" with no Ravi in the family yet.
    public static let raviAsk: GlanceItem = decode(#"""
    {"key":"ask:ravi mama","kind":"ask","title":"Ravi mama","term":"Ravi mama","guess":"Ravi",
     "suggestions":[{"owner":"p_arjun_3","relation":"mother.younger_brother","label":"Mom's younger brother"},
                    {"owner":"p_arjun_3","relation":"mother.elder_brother","label":"Mom's elder brother"},
                    {"owner":"p_arjun_3","relation":"father.elder_sister.husband","label":"Dad's sister's husband"}]}
    """#)
    public static let murukku: GlanceItem = decode(#"""
    {"key":"lex:ta:murukku","kind":"term","title":"Murukku","native":"முறுக்கு","body":"Crunchy spirals of rice flour, fried. A festival snack.","category":"food"}
    """#)
    // Story 9: Paatti's own screen, in Tamil, when Arjun mentions Mei.
    public static let meiForPaatti: GlanceItem = decode(#"""
    {"key":"who:p_mei_5","kind":"who","title":"மெய்","native":"Mei","body":"அர்ஜுனின் பள்ளித் தோழி, இப்போது ஷாங்காயில்","category":"person","node_id":"p_mei_5","gap":"new"}
    """#)
    // Story 7
    public static let thinMeaning: PragmaticsCard = decode(#"""
    {"kind":"cultural","source":"ரொம்ப இளைச்சுட்ட","literal":"You've gotten so thin","meaning":"She's worried you aren't eating well. It's care, not criticism.","why_it_matters":"Grandparents show love through food."}
    """#)

    public static let meiHello: Transcript = decode(#"""
    {"call_id":12,"utterance_id":90,"speaker":"p_mei_5","speaker_identity":"p5","src_text":"最近怎么样？我这周忙死了","src_lang":"zh","target_lang":"en","translation":"How have you been? This week has been crazy."}
    """#)
    public static let meiLin: Transcript = decode(#"""
    {"call_id":12,"utterance_id":91,"speaker":"p_mei_5","speaker_identity":"p5","role":"participant","listener":"p_arjun_3",
     "src_text":"我和林终于去莫干山攀岩了","src_lang":"zh","target_lang":"en","translation":"Lin and I finally went climbing at Moganshan.",
     "grounded_spans":[{"source":"林","rendered":"Mei's friend Lin (from the Fudan climbing wall)","node_id":"p_lin_17"}],"pragmatics_cards":[],"confidence":0.9}
    """#)
    public static let meiByteDance: Transcript = decode(#"""
    {"call_id":12,"utterance_id":95,"speaker":"p_mei_5","speaker_identity":"p5","src_text":"字节那边还没消息，好紧张","src_lang":"zh","target_lang":"en","translation":"Still no news from ByteDance. I'm so nervous."}
    """#)
    public static let paattiRavi: Transcript = decode(#"""
    {"call_id":14,"utterance_id":201,"speaker":"p_paatti_2","speaker_identity":"p2","src_text":"ரவி நேத்து அடையாறுலேர்ந்து போன் பண்ணான்","src_lang":"ta","target_lang":"en","translation":"Ravi mama called yesterday from Adyar.",
     "grounded_spans":[{"source":"ரவி","rendered":"your uncle Ravi mama (Mom's younger brother)","node_id":"p_ravi_mama_8"}]}
    """#)
    public static let paattiThin: Transcript = decode(#"""
    {"call_id":14,"utterance_id":202,"speaker":"p_paatti_2","speaker_identity":"p2","src_text":"ரொம்ப இளைச்சுட்ட, சரியா சாப்பிடுறியா?","src_lang":"ta","target_lang":"en","translation":"You've gotten so thin. Are you eating properly?"}
    """#)
    public static let paattiRaviMama: Transcript = decode(#"""
    {"call_id":14,"utterance_id":210,"speaker":"p_paatti_2","speaker_identity":"p2","src_text":"ரவி மாமா நாளைக்கு வீட்டுக்கு வர்றான்","src_lang":"ta","target_lang":"en","translation":"Ravi mama is coming over tomorrow."}
    """#)
    public static let paattiMurukku: Transcript = decode(#"""
    {"call_id":14,"utterance_id":204,"speaker":"p_paatti_2","speaker_identity":"p2","src_text":"உனக்காக முறுக்கு செஞ்சு வச்சிருக்கேன்","src_lang":"ta","target_lang":"en","translation":"I've made murukku for you."}
    """#)
    public static let arjunHikeForPaatti: Transcript = decode(#"""
    {"call_id":14,"utterance_id":220,"speaker":"p_arjun_3","speaker_identity":"p3","src_text":"Mei and I went hiking when she visited.","src_lang":"en","target_lang":"ta","translation":"மெய்யும் நானும் அவள் வந்தபோது மலையேற்றம் போனோம்."}
    """#)
    public static let priyaJess: Transcript = decode(#"""
    {"call_id":16,"utterance_id":301,"speaker":"p_priya_4","speaker_identity":"p4","src_text":"Jess and I finally painted the whole dorm room.","src_lang":"en","target_lang":"en","translation":null}
    """#)
    public static let jessNew: GlanceItem = decode(#"""
    {"key":"who:p_jess_22","kind":"who","title":"Jess","native":"","body":"Priya's roommate at Georgia Tech","category":"person","node_id":"p_jess_22","gap":"new"}
    """#)

    // Film shot 7: Mei's own phone. Arjun's English arrives as a Chinese caption; Mei gets no card.
    public static let arjunBoulderForMei: Transcript = decode(#"""
    {"call_id":12,"utterance_id":92,"speaker":"p_arjun_3","speaker_identity":"p3","src_text":"Oh, I actually started bouldering!","src_lang":"en","target_lang":"zh","translation":"哦，我其实开始玩抱石了！"}
    """#)
    public static let arjunHowLinForMei: Transcript = decode(#"""
    {"call_id":12,"utterance_id":93,"speaker":"p_arjun_3","speaker_identity":"p3","src_text":"Wait, how was Moganshan?","src_lang":"en","target_lang":"zh","translation":"等等，莫干山怎么样？"}
    """#)
    // Film shot 10: the two Ravis, each named with who he is to Arjun.
    public static let paattiRaviMamaGrounded: Transcript = decode(#"""
    {"call_id":14,"utterance_id":201,"speaker":"p_paatti_2","speaker_identity":"p2","src_text":"ரவி நேத்து அடையாறுலேர்ந்து போன் பண்ணான்","src_lang":"ta","target_lang":"en","translation":"Ravi mama (Mom's younger brother) called yesterday from Adyar."}
    """#)
    public static let paattiRaviPeriyappa: Transcript = decode(#"""
    {"call_id":14,"utterance_id":203,"speaker":"p_paatti_2","speaker_identity":"p2","src_text":"ரவி கோவையில புது கடை திறந்திருக்காரு","src_lang":"ta","target_lang":"en","translation":"Ravi periyappa (Dad's elder brother) opened a new shop in Kovai.",
     "grounded_spans":[{"source":"ரவி","rendered":"your uncle Ravi periyappa (Dad's elder brother)","node_id":"p_ravi_periyappa_9"}]}
    """#)
    public static let paattiFriends: Transcript = decode(#"""
    {"call_id":14,"utterance_id":215,"speaker":"p_paatti_2","speaker_identity":"p2","src_text":"உன் ஃப்ரெண்ட்ஸ் எல்லாம் எப்படி இருக்காங்க?","src_lang":"ta","target_lang":"en","translation":"How are all your friends doing?"}
    """#)
    public static let hikeBridge: GlanceItem = decode(#"""
    {"key":"bridge:38","kind":"bridge","title":"Paatti hasn't heard yet","body":"you went hiking with Mei when she visited","target":"p_paatti_2","private":true}
    """#)
}
