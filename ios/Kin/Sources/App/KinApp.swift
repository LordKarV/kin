import SwiftUI

@main
struct KinApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .onOpenURL { model.open($0) }
                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                    if let url = activity.webpageURL { model.open(url) }
                }
                .preferredColorScheme(.dark)
        }
    }
}

struct RootView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            switch model.screen {
            case .signup: SignupView(model: model)
            case .home: HomeView(model: model)
            case .call(let call): CallView(call: call, invite: model.inviteURL(callId: call.callId))
            case .ended(let id): EndedView(callId: id, onHome: model.backHome)
            }
        }
        .alert("KIN", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(model.error ?? "")
        }
    }
}

struct EndedView: View {
    let callId: Int
    let onHome: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Spacer()
            Text("Call ended").font(.largeTitle.bold())
            Spacer()
            PillButton(title: "Back home", systemImage: "house", action: onHome)
        }
        .padding(24)
    }
}
