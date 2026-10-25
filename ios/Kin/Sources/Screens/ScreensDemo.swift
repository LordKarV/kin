#if DEBUG
import SwiftUI

/// `-demoState people|world|messages`: the app screens with the demo cast, no networking (simulator screenshots).
/// The data is wire JSON decoded through the real types, so a contract change breaks the demo, not silently.
@MainActor
enum ScreensDemo {
    static func decode<T: Decodable>(_ json: String) -> T {
        do { return try JSONDecoder().decode(T.self, from: Data(json.utf8)) } catch { fatalError("demo JSON: \(T.self): \(error)") }
    }

    static let contacts: [ContactOut] = decode(#"""
    [{"person":"p_paatti_2","name":"Kamala Paatti","lang":"ta","render":"Your grandmother","circle":"family"},
     {"person":"p_mei_5","name":"Mei","lang":"zh","render":"Close friend from high school","circle":"friends"},
     {"person":"p_priya_4","name":"Priya","lang":"en","render":"Friend from high school","circle":"friends"}]
    """#)

    static let world: WorldOut = decode(#"""
    {"me":"p_arjun_3",
     "people":[{"id":3,"person":"p_arjun_3","name":"Arjun","render":"You","lang":"en","is_user":true,"circle":null},
               {"id":5,"person":"p_mei_5","name":"Mei","render":"Close friend from high school","lang":"zh","is_user":true,"circle":"friends"},
               {"id":17,"person":"p_lin_17","name":"Lin","render":"Her friend from the Fudan climbing wall","lang":"zh","is_user":false,"circle":null},
               {"id":21,"person":"p_sato_21","name":"Sato","render":"Her dorm roommate","lang":"ja","is_user":false,"circle":null}],
     "ties":[{"src":"p_mei_5","dst":"p_lin_17","kind":"friend","context":"Fudan climbing wall"},
             {"src":"p_mei_5","dst":"p_sato_21","kind":"roommate","context":""}],
     "edges":[],"groups":[],
     "things":[{"id":4,"slug":"t_shanghai_4","kind":"place","name":"Shanghai","owner":"p_mei_5"}],
     "storylines":[{"id":3,"title":"Mei's job search","status":"open",
                    "states":[{"label":"applied to ByteDance","at":"2026-09-02"},{"label":"second-round interview","at":"2026-10-10"}]}]}
    """#)

    static let facts: FactsOut = decode(#"""
    {"about_me":[
      {"id":41,"text":"started bouldering","subject":"p_arjun_3","speaker":"p_arjun_3","source_kind":"sms","said_at":"2026-10-03T18:20:00","status":"active","sensitive_kind":"","pinned":false,"expires_at":null,"heard_by":[{"person":"p_arjun_3","name":"Arjun","via":"authored"},{"person":"p_priya_4","name":"Priya","via":"call"}]},
      {"id":44,"text":"got an internship offer","subject":"p_arjun_3","speaker":"p_arjun_3","source_kind":"sms","said_at":"2026-10-21T09:02:00","status":"active","sensitive_kind":"","pinned":false,"expires_at":null,"heard_by":[{"person":"p_arjun_3","name":"Arjun","via":"authored"}]}],
     "i_said":[
      {"id":38,"text":"Mei is my close friend from high school","subject":"p_mei_5","speaker":"p_arjun_3","source_kind":"call","said_at":"2026-09-28T20:00:00","status":"active","sensitive_kind":"","pinned":false,"expires_at":null,"heard_by":[]}]}
    """#)

    static func view(_ name: String) -> AnyView? {
        switch name {
        case "people":
            return AnyView(tabs(.people) {
                PeopleList(contacts: contacts, error: nil, myLang: "en", joining: false, onCall: {}, retry: {}) { _ in EmptyView() }
            })
        case "world":
            let mei = contacts[1]
            return AnyView(tabs(.people) {
                PersonWorldView(contact: mei, world: PersonWorld.build(slug: mei.person, name: mei.name, world: world, facts: facts),
                                error: nil, joining: false, actions: PersonWorldActions())
            })
        case "messages":
            return AnyView(tabs(.messages) {
                MessagesView(number: "+1 (512) 555-0142", understood: MessagesScreen.fromTexts(facts), error: nil,
                             onEdit: { _ in }, onDelete: { _ in }, retry: {})
            })
        default:
            return nil
        }
    }

    enum Tab { case people, messages }

    private static func tabs<V: View>(_ selected: Tab, @ViewBuilder _ content: () -> V) -> some View {
        let page = NavigationStack { content() }
        return TabView(selection: .constant(selected)) {
            Group { if selected == .people { page } else { Color.clear } }
                .tabItem { Label("People", systemImage: "person.2.fill") }.tag(Tab.people)
            Group { if selected == .messages { page } else { Color.clear } }
                .tabItem { Label("Messages", systemImage: "bubble.left.and.text.bubble.right.fill") }.tag(Tab.messages)
        }
        .tint(K.link)
    }
}
#endif
