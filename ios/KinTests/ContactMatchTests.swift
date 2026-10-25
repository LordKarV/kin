import XCTest
@testable import Kin

/// Contact matching must normalize and hash exactly like the backend (world.users.normalize_phone + sha256).
final class ContactMatchTests: XCTestCase {
    func testNormalizeMatchesServerRules() {
        for raw in ["+15125550100", "(512) 555-0100", "1 512 555 0100", "+1 512-555-0100", "\u{0665}\u{0661}\u{0662}5550100"] {
            XCTAssertEqual(ContactMatch.normalize(raw), "+15125550100", raw)
        }
        XCTAssertEqual(ContactMatch.normalize("+44 20 7946 0958"), "+442079460958")
        XCTAssertNil(ContactMatch.normalize("555-01"))
        XCTAssertNil(ContactMatch.normalize(""))
    }

    func testHashIsLowercaseSha256OfE164() {
        // python3 -c "import hashlib;print(hashlib.sha256(b'+15125550100').hexdigest())"
        let known = "12945b229096fbeea14e73ff7096d927765584b9663358877238f4075eba0d89"
        XCTAssertEqual(ContactMatch.hash("+15125550100"), known)
        XCTAssertEqual(ContactMatch.hashes(of: ["(512) 555-0100", "+1 512 555 0100", "12"]), [known])
    }
}
