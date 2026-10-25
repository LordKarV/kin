import Foundation
import os

/// WS /ws/events: the server tells this user about rings. No push (no paid Apple account), so it only runs while the
/// app is open (or ringing in the background); AppModel starts and stops it. Reconnects with backoff (1 s doubling to
/// 30 s); the server pings every 25 s, which keeps the connection from idling out.
actor EventSocket {
    static let maxBackoff: Double = 30
    private static let log = Logger(subsystem: "dev.kin.app", category: "events")

    /// Built again for every attempt, so a KIN key saved after the socket started (an invite's) is used on reconnect.
    private let makeRequest: @Sendable () -> URLRequest?
    private let onEvent: @Sendable (CallEvent) async -> Void
    private var loop: Task<Void, Never>?
    private var socket: URLSessionWebSocketTask?

    init(makeRequest: @escaping @Sendable () -> URLRequest?, onEvent: @escaping @Sendable (CallEvent) async -> Void) {
        self.makeRequest = makeRequest
        self.onEvent = onEvent
    }

    /// ws(s)://<server>/ws/events with the token and KIN key as headers, which keeps them out of access logs.
    nonisolated static func request(base: URL, token: String, apiKey: String?) -> URLRequest? {
        guard let url = URL(string: "/ws/events", relativeTo: base),
              var c = URLComponents(url: url.absoluteURL, resolvingAgainstBaseURL: false) else { return nil }
        c.scheme = c.scheme == "https" ? "wss" : "ws"
        guard let wsURL = c.url else { return nil }
        var r = URLRequest(url: wsURL)
        r.setValue(token, forHTTPHeaderField: "X-KIN-User")
        if let apiKey, !apiKey.isEmpty { r.setValue(apiKey, forHTTPHeaderField: "X-KIN-Key") }
        return r
    }

    nonisolated static func backoff(attempt: Int) -> Double { min(maxBackoff, pow(2, Double(min(attempt, 8)))) }

    func start() {
        guard loop == nil else { return }
        loop = Task { await run() }
    }

    func stop() {
        loop?.cancel()
        loop = nil
        socket?.cancel(with: .goingAway, reason: nil)  // receive() ignores task cancellation; this wakes it
        socket = nil
    }

    private func run() async {
        var attempt = 0
        while !Task.isCancelled, let request = makeRequest() {  // nil: signed out
            let ws = URLSession.shared.webSocketTask(with: request)
            socket = ws
            ws.resume()
            do {
                while true {
                    let data: Data
                    switch try await ws.receive() {
                    case .string(let s): data = Data(s.utf8)
                    case .data(let d): data = d
                    @unknown default: continue
                    }
                    attempt = 0  // the connection works
                    if let event = CallEvent.decode(data) { await onEvent(event) }
                }
            } catch {
                if Task.isCancelled { break }
                Self.log.info("event socket closed (\(ws.closeCode.rawValue)): \(error.localizedDescription)")
            }
            try? await Task.sleep(for: .seconds(Self.backoff(attempt: attempt)))
            attempt += 1
        }
    }
}
