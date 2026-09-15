#if DEBUG
import AppKit
import Foundation

/// QA-only UI stress driver. Enabled with `-bsh.qaStress YES` (DEBUG builds only).
/// Cycles tabs, blotter, companies, tickers, sheets and languages every 150-300 ms for ~3 minutes.
/// With `-bsh.qaSnapshotDir <dir>` it instead renders every app window to PNG plus an
/// accessibility text dump (works while the screen is locked, where screencapture is black).
@MainActor
enum MacQAStress {
    private static var running = false

    static func start(store: MacAppStore) {
        guard !running else { return }
        running = true
        if let dir = UserDefaults.standard.string(forKey: "bsh.qaSnapshotDir"), !dir.isEmpty {
            snapshotLoop(dir: dir)
            return
        }
        let duration = UserDefaults.standard.double(forKey: "bsh.qaStressSeconds") > 0
            ? UserDefaults.standard.double(forKey: "bsh.qaStressSeconds") : 180
        NSLog("QASTRESS start duration=%.0f companies=%d", duration, store.companies.count)
        qaLog(String(format: "start duration=%.0f companies=%d", duration, store.companies.count))
        Task { @MainActor [weak store] in
            let started = Date()
            let tabs = MacTab.allCases
            let blotterTabs = MacBlotterTab.allCases
            let tickers = ["AAPL", "MSFT", "NVDA", "BRK.B", "ZABKY"]
            var step = 0
            let defaults = UserDefaults.standard
            let allowed = Set((defaults.string(forKey: "bsh.qaStressActions") ?? "")
                .split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty })
            let noTabs = defaults.bool(forKey: "bsh.qaStressNoTabs")
            let noCompany = defaults.bool(forKey: "bsh.qaStressNoCompany")
            qaLog("config actions=\(allowed.isEmpty ? "all" : allowed.sorted().joined(separator: ",")) noTabs=\(noTabs) noCompany=\(noCompany)")
            while Date().timeIntervalSince(started) < duration {
                guard let store else { return }
                step += 1
                let action = ["palette-open", "palette-close", "firm-open", "firm-close", "decision-open", "decision-close", "blotter-toggle", "blotter-tab", "language", "ticker"][step % 10]
                qaLog(String(format: "step=%d t=%.2f tab=%@ action=%@ blotter=%d/%@ company=%@", step, Date().timeIntervalSince(started), tabs[step % tabs.count].rawValue, action, store.showBlotter ? 1 : 0, store.blotterTab.rawValue, store.companies.isEmpty ? "-" : store.companies[step % store.companies.count].id))
                if !noTabs { store.selectedTab = tabs[step % tabs.count] }
                let companies = store.companies
                if !noCompany, !companies.isEmpty {
                    store.selectCompany(companies[step % companies.count])
                }
                if !allowed.isEmpty, !allowed.contains(action) {
                    try? await Task.sleep(nanoseconds: UInt64(Int.random(in: 150...300)) * 1_000_000)
                    continue
                }
                switch step % 10 {
                case 0: store.openCommandPalette(seed: step % 20 == 0 ? "a" : "")
                case 1: store.showCommandPalette = false
                case 2: store.showFirmSearch = true
                case 3: store.showFirmSearch = false
                case 4:
                    if let c = store.selectedCompany ?? companies.first { store.requestDecision(for: c) }
                case 5: store.showDecisionSheet = false
                case 6: store.showBlotter.toggle()
                case 7: store.blotterTab = blotterTabs[(step / 10) % blotterTabs.count]
                case 8:
                    store.readerLanguage = store.readerLanguage == "en" ? "zh" : "en"
                    store.pulseLanguage = store.pulseLanguage == "en" ? "zh" : "en"
                default: store.selectTicker(tickers[(step / 10) % tickers.count])
                }
                if step % 20 == 0 {
                    NSLog("QASTRESS step=%d t=%.1f tab=%@ blotter=%d/%@ company=%@ lang=%@",
                          step, Date().timeIntervalSince(started), store.selectedTab.rawValue,
                          store.showBlotter ? 1 : 0, store.blotterTab.rawValue,
                          store.selectedCompany?.id ?? "-", store.readerLanguage)
                }
                try? await Task.sleep(nanoseconds: UInt64(Int.random(in: 150...300)) * 1_000_000)
            }
            store?.showCommandPalette = false
            store?.showFirmSearch = false
            store?.showDecisionSheet = false
            store?.selectedTab = .home
            NSLog("QASTRESS done steps=%d", step)
            qaLog("done steps=\(step)")
            running = false
        }
    }

    /// Renders all windows (including attached sheets) and dumps their accessibility text.
    private static func snapshotLoop(dir: String) {
        let delay = UserDefaults.standard.double(forKey: "bsh.qaSnapshotDelay") > 0
            ? UserDefaults.standard.double(forKey: "bsh.qaSnapshotDelay") : 10
        let count = max(1, UserDefaults.standard.integer(forKey: "bsh.qaSnapshotCount"))
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        Task { @MainActor in
            for round in 0..<count {
                try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                for (index, window) in NSApp.windows.enumerated() where window.isVisible {
                    let safeTitle = window.title.replacingOccurrences(of: "/", with: "_")
                    let base = (dir as NSString).appendingPathComponent("r\(round)-w\(index)-\(safeTitle)")
                    var lines: [String] = []
                    dumpAX(window, depth: 0, into: &lines)
                    try? lines.joined(separator: "\n").write(toFile: base + ".txt", atomically: true, encoding: .utf8)
                    NSLog("QASNAP wrote %@ lines=%d sheet=%d", base, lines.count, window.isSheet ? 1 : 0)
                }
            }
            NSLog("QASNAP done")
            running = false
        }
    }

    private static func writeLayerPNG(view: NSView, path: String) {
        view.wantsLayer = true
        guard let layer = view.layer else { return }
        let scale = view.window?.backingScaleFactor ?? 2
        let size = view.bounds.size
        let w = Int(size.width * scale), h = Int(size.height * scale)
        guard w > 2, h > 2,
              let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return }
        ctx.setFillColor(NSColor.windowBackgroundColor.cgColor)
        ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
        ctx.scaleBy(x: scale, y: scale)
        if !layer.isGeometryFlipped {
            ctx.translateBy(x: 0, y: size.height)
            ctx.scaleBy(x: 1, y: -1)
        }
        layer.render(in: ctx)
        guard let image = ctx.makeImage() else { return }
        let rep = NSBitmapImageRep(cgImage: image)
        if let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: path))
        }
    }

    /// Appends one line to `-bsh.qaStressLog <file>` (NSLog does not reach `log show` for this build).
    private static func qaLog(_ line: String) {
        guard let path = UserDefaults.standard.string(forKey: "bsh.qaStressLog"), !path.isEmpty else { return }
        let text = "\(Date().timeIntervalSince1970) \(line)\n"
        if let handle = FileHandle(forWritingAtPath: path) {
            handle.seekToEndOfFile()
            handle.write(Data(text.utf8))
            try? handle.synchronize()
            try? handle.close()
        } else {
            FileManager.default.createFile(atPath: path, contents: Data(text.utf8))
        }
    }

    private static func dumpAX(_ element: Any, depth: Int, into lines: inout [String]) {
        guard depth < 40, lines.count < 4000, let el = element as? NSAccessibilityProtocol else { return }
        let role = el.accessibilityRole()?.rawValue ?? ""
        let label = el.accessibilityLabel() ?? ""
        let title = el.accessibilityTitle() ?? ""
        var valueText = ""
        if let v = el.accessibilityValue() { valueText = "\(v)" }
        let frame = el.accessibilityFrame()
        if !(label.isEmpty && title.isEmpty && valueText.isEmpty) || role.contains("Progress") || role.contains("Button") {
            lines.append(String(repeating: " ", count: depth) + "\(role) [\(title)] [\(label)] =\(valueText.prefix(160)) @\(Int(frame.minX)),\(Int(frame.minY)) \(Int(frame.width))x\(Int(frame.height))")
        }
        for child in el.accessibilityChildren() ?? [] { dumpAX(child, depth: depth + 1, into: &lines) }
    }
}
#endif
