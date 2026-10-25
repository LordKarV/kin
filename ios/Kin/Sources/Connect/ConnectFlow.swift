import Foundation

/// What sending a request to a handle came to, as the Add person sheet shows it.
enum ConnectOutcome: Equatable {
    case sent(name: String)
    case connected(name: String)
    case noOne
    case failed(String)

    var message: String {
        switch self {
        case .sent(let name): return "Request sent to \(name)."
        case .connected(let name): return "Connected with \(name). Call them from People."
        case .noOne: return "No one with that handle."
        case .failed(let why): return "Could not send: \(why)"
        }
    }

    var isConnected: Bool { if case .connected = self { return true } else { return false } }
    var isError: Bool {
        switch self {
        case .noOne, .failed: return true
        case .sent, .connected: return false
        }
    }
}

enum ConnectFlow {
    /// POST /api/connect for a typed handle. nil when the field is blank (nothing sent).
    static func send(_ typed: String, via api: KinAPI) async -> ConnectOutcome? {
        let handle = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !handle.isEmpty else { return nil }
        do {
            let out = try await api.connect(handle: handle)
            return out.status == "accepted" ? .connected(name: out.user.name) : .sent(name: out.user.name)
        } catch let e as KinAPIError where e.status == 404 {
            return .noOne
        } catch {
            return .failed(error.localizedDescription)
        }
    }
}
