import SwiftUI

/// Every non-call screen, in render order.
public enum Screens {
    @MainActor public static var all: [(String, AnyView)] {
        [
            ("app-01-setup-name", AnyView(PhoneChrome(dark: false) { Setup.name })),
            ("app-02-setup-first-person", AnyView(PhoneChrome(dark: false) { Setup.firstPerson })),
            ("app-03-setup-promise", AnyView(PhoneChrome(dark: false) { Setup.promise })),
            ("app-04-people", AnyView(PhoneChrome(dark: false) { PeopleScreen(contacts: Sample.contacts) })),
            ("app-05-people-empty", AnyView(PhoneChrome(dark: false) { PeopleEmptyScreen() })),
            ("app-06-person-world", AnyView(PhoneChrome(dark: false) { PersonWorldScreen() })),
            ("app-07-messages", AnyView(PhoneChrome(dark: false) { MessagesScreen() })),
            ("app-08-you-privacy", AnyView(PhoneChrome(dark: false) { YouScreen(facts: Sample.myFacts, thirdParty: Sample.thirdParty, contacts: Sample.contacts) })),
            ("app-09-people-dark", AnyView(PhoneChrome(dark: true) { PeopleScreen(contacts: Sample.contacts) })),
            ("app-10-person-world-dark", AnyView(PhoneChrome(dark: true) { PersonWorldScreen() })),
            ("app-11-invited-signup", AnyView(PhoneChrome(dark: false) { InvitedSignupScreen() })),
            ("app-12-welcome-sms", AnyView(PhoneChrome(dark: false) { WelcomeScreen() })),
            ("app-13-add-relative", AnyView(PhoneChrome(dark: false) { AddRelativeScreen() })),
            ("app-14-call-ended", AnyView(PhoneChrome(dark: false) { CallEndedScreen() })),
            ("app-15-delete-confirm", AnyView(PhoneChrome(dark: false) { DeleteConfirmScreen() })),
        ]
    }
}
