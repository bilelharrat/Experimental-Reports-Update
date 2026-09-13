import Foundation
import Combine
import SwiftUI

/// Legendary investor persona for the Ask experience (name + portrait).
enum AskInvestor: String, CaseIterable, Identifiable, Hashable {
    case buffett
    case munger
    case graham
    case simons
    case soros

    var id: String { rawValue }

    /// Asset catalog image name.
    var imageName: String {
        switch self {
        case .buffett: return "AskBuffett"
        case .munger: return "AskMunger"
        case .graham: return "AskGraham"
        case .simons: return "AskSimons"
        case .soros: return "AskSoros"
        }
    }

    var fullName: String {
        switch self {
        case .buffett: return "Warren Buffett"
        case .munger: return "Charlie Munger"
        case .graham: return "Benjamin Graham"
        case .simons: return "Jim Simons"
        case .soros: return "George Soros"
        }
    }

    var firstName: String {
        switch self {
        case .buffett: return "Warren"
        case .munger: return "Charlie"
        case .graham: return "Benjamin"
        case .simons: return "Jim"
        case .soros: return "George"
        }
    }

    /// Status while the model is streaming.
    var thinkingLabel: String {
        switch self {
        case .buffett: return "Buffetting…"
        case .munger: return "Mungering…"
        case .graham: return "Grahamming…"
        case .simons: return "Simonsing…"
        case .soros: return "Sorosing…"
        }
    }

    func inviteTitle(lang: AppLanguage) -> String {
        switch lang {
        case .en:
            return "Ask \(firstName)"
        case .zh:
            switch self {
            case .buffett: return "问沃伦"
            case .munger: return "问查理"
            case .graham: return "问本杰明"
            case .simons: return "问吉姆"
            case .soros: return "问乔治"
            }
        case .hi:
            return "\(firstName) से पूछें"
        case .es:
            return "Preguntar a \(firstName)"
        case .fr:
            return "Demander à \(firstName)"
        case .ar:
            return "اسأل \(firstName)"
        case .bn:
            return "\(firstName)-কে জিজ্ঞাসা করুন"
        case .pt:
            return "Perguntar a \(firstName)"
        case .ru:
            switch self {
            case .buffett: return "Спросить Уоррена"
            case .munger: return "Спросить Чарли"
            case .graham: return "Спросить Бенджамина"
            case .simons: return "Спросить Джима"
            case .soros: return "Спросить Джорджа"
            }
        case .ur:
            return "\(firstName) سے پوچھیں"
        }
    }

    func thinkingLabel(lang: AppLanguage) -> String {
        switch lang {
        case .en:
            return thinkingLabel
        case .zh:
            switch self {
            case .buffett: return "巴菲特中…"
            case .munger: return "芒格中…"
            case .graham: return "格雷厄姆中…"
            case .simons: return "西蒙斯中…"
            case .soros: return "索罗斯中…"
            }
        case .hi, .es, .fr, .ar, .bn, .pt, .ru, .ur:
            // Playful English gerunds stay brand-recognizable across locales.
            return thinkingLabel
        }
    }

    /// Map retired persona keys from older builds.
    static func resolved(fromRaw raw: String?) -> AskInvestor {
        switch raw {
        case "lynch": return .simons
        case "templeton": return .soros
        default:
            return AskInvestor(rawValue: raw ?? "") ?? .buffett
        }
    }
}

@MainActor
final class AskPersonaStore: ObservableObject {
    @Published var investor: AskInvestor {
        didSet { UserDefaults.standard.set(investor.rawValue, forKey: "bsh.askInvestor") }
    }

    init() {
        let raw = UserDefaults.standard.string(forKey: "bsh.askInvestor")
        investor = AskInvestor.resolved(fromRaw: raw)
    }
}
