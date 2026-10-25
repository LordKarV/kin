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
        }
    }
}

struct RootView: View {
    @ObservedObject var model: AppModel
    @Environment(\.scenePhase) private var scenePhase

    /// The redesigned People/Messages screens follow the system light/dark setting; sign-up and the ended screen
    /// still use the dark-only App/Theme tokens, and the call screen is always dark.
    private var isTabs: Bool {
        if case .home = model.screen { return true }
        return false
    }

    var body: some View {
        ZStack {
            #if DEBUG
            if CallDemo.isRequested { CallDemo.view() } else { screen }
            #else
            screen
            #endif
        }
        .preferredColorScheme(isTabs || demoFollowsSystem ? nil : .dark)
        .onChange(of: scenePhase, initial: true) { _, phase in
            model.scene(active: phase == .active ? true : phase == .background ? false : nil)
        }
        // Ringing covers any screen (calling someone, or someone calling me); Calling/RingViews.swift.
        .fullScreenCover(isPresented: Binding(get: { model.ring != .idle }, set: { if !$0 { model.send(.dismiss) } })) {
            RingScreen(model: model)
        }
        .alert("KIN", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(model.error ?? "")
        }
    }
}

extension RootView {
    @ViewBuilder var screen: some View {
        switch model.screen {
        case .signup: SignupView(model: model).background(Theme.background.ignoresSafeArea())
        case .home: MainTabs(model: model)
        case .call(let call): CallView(call: call, invite: model.inviteURL(callId: call.callId))
        case .ended(let id): EndedView(callId: id, onHome: model.backHome).background(Theme.background.ignoresSafeArea())
        }
    }

    /// Demo app screens render in the system appearance like the real tabs.
    var demoFollowsSystem: Bool {
        #if DEBUG
        return CallDemo.isRequested && ["people", "world", "messages"].contains(CallDemo.requestedState)
        #else
        return false
        #endif
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
