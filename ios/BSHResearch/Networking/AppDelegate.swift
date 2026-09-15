import Foundation
import UIKit
import UserNotifications

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        PushRegistrar.requestAuthorizationAndRegister()
        return true
    }

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        PushRegistrar.upload(deviceToken: deviceToken)
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        #if DEBUG
        print("APNs registration failed: \(error.localizedDescription)")
        #endif
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .badge])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let info = response.notification.request.content.userInfo
        if let link = info["deep_link"] as? String, let url = URL(string: link),
           let deep = DeepLink(url: url) {
            Task { @MainActor in
                NotificationCenter.default.post(
                    name: .bshOpenDeepLink,
                    object: deep
                )
            }
        }
        completionHandler()
    }
}

extension Notification.Name {
    static let bshOpenDeepLink = Notification.Name("bshOpenDeepLink")
    /// Fired after API base URL change / explicit Sync — Home and desks should reload from the live server.
    static let bshServerDidSync = Notification.Name("bshServerDidSync")
}

enum PushRegistrar {
    struct DeviceTokenBody: Encodable {
        let token: String
        let platform: String
        let topics: [String]
    }

    static func requestAuthorizationAndRegister() {
        // Personal team cannot provision Push (aps-environment). Re-enable by
        // adding SWIFT_ACTIVE_COMPILATION_CONDITIONS = BSH_ENABLE_REMOTE_PUSH
        // and restoring aps-environment once on a paid Developer Program team.
        #if BSH_ENABLE_REMOTE_PUSH
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
        #endif
    }

    static func upload(deviceToken: Data) {
        let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
        UserDefaults.standard.set(hex, forKey: "bsh.apns.token")
        Task {
            do {
                let body = DeviceTokenBody(
                    token: hex,
                    platform: "ios",
                    topics: ["memo", "brief", "ask", "alert", "mover"]
                )
                struct DeviceTokenResponse: Decodable { let ok: Bool? }
                let _: DeviceTokenResponse = try await APIClient.shared.post("device-tokens", body: body)
            } catch {
                #if DEBUG
                print("device token upload failed: \(error)")
                #endif
            }
        }
    }
}
