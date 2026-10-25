import XCTest
@testable import Kin

final class AppHandoffTests: XCTestCase {
    private let key = MessagesScreen.savedNumberKey

    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: key)
        super.tearDown()
    }

    private func signup(sms: String?) -> UserOut {
        UserOut(userId: 1, personId: 2, person: "Arjun", spaceId: 3, token: "t", smsNumber: sms)
    }

    @MainActor func testSignupSavesTheSmsNumberMessagesScreenReads() {
        SignupView.saveSmsNumber(signup(sms: "+15125550100"))
        XCTAssertEqual(UserDefaults.standard.string(forKey: key), "+15125550100")
    }

    // A stale number from an earlier sign-up must not outlive a sign-up that has none.
    @MainActor func testNilSmsNumberClearsTheSavedNumber() {
        UserDefaults.standard.set("+15125550199", forKey: key)
        SignupView.saveSmsNumber(signup(sms: nil))
        XCTAssertNil(UserDefaults.standard.object(forKey: key))
    }

    // config.py sends "" when no number is configured; saving it would be noise over GET /api/me.
    @MainActor func testEmptySmsNumberIsNotSaved() {
        UserDefaults.standard.set("+15125550199", forKey: key)
        SignupView.saveSmsNumber(signup(sms: ""))
        XCTAssertNil(UserDefaults.standard.object(forKey: key))
    }
}
