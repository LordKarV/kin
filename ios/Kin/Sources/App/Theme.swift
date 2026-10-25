import SwiftUI

/// Visual tokens until the design pass (docs/collab/DESIGN_BRIEF.md) lands. Views use only these.
enum Theme {
    static let background = Color(hex: 0x18191A)
    static let surface = Color(hex: 0x242526)
    static let field = Color(hex: 0x3A3B3C)
    static let primary = Color(hex: 0x0064E0)
    static let primaryEnd = Color(hex: 0x0082FB)
    static let accent = Color(hex: 0x47A5FA)
    static let success = Color(hex: 0x31A24C)
    static let warning = Color(hex: 0xF7B928)
    static let error = Color(hex: 0xE41E3F)
    static let radiusLarge: CGFloat = 20
    static let radius: CGFloat = 14
    static let radiusSmall: CGFloat = 8
    static let primaryGradient = LinearGradient(colors: [primary, primaryEnd], startPoint: .leading, endPoint: .trailing)
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }
}

/// Pill button. `primary` is the gradient call-to-action; otherwise a field-colored pill.
struct PillButton: View {
    let title: String
    var systemImage: String?
    var primary = true
    var busy = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if busy { ProgressView().tint(.white) } else if let systemImage { Image(systemName: systemImage) }
                Text(title).font(.headline)
            }
            .frame(maxWidth: .infinity, minHeight: 50)
            .foregroundStyle(.white)
            .background(primary ? AnyShapeStyle(Theme.primaryGradient) : AnyShapeStyle(Theme.field), in: Capsule())
        }
        .disabled(busy)
    }
}

/// A labeled text field on the field color.
struct KinField: View {
    let label: String
    @Binding var text: String
    var keyboard: UIKeyboardType = .default

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.subheadline).foregroundStyle(.secondary)
            TextField(label, text: $text)
                .keyboardType(keyboard)
                .padding(12)
                .background(Theme.field, in: RoundedRectangle(cornerRadius: Theme.radiusSmall))
        }
    }
}

/// Error line in the error color; hidden when nil.
struct ErrorText: View {
    let message: String?
    var body: some View {
        if let message { Text(message).font(.footnote).foregroundStyle(Theme.error) }
    }
}
