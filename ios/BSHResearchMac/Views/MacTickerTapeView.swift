import AppKit
import SwiftUI

/// Bloomberg-style ticker tape: the desk watchlist scrolling in a single line.
/// Pure presentation — quotes come from the same `store.watchlist` Market Radar uses.
/// The strip is laid out once per quote change and scrolled by a single Core Animation
/// layer animation, so a visible tape does no per-frame work in the app.
struct MacTickerTapeView: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var speed: CGFloat = 40   // points per second

    private var entries: [MacTapeEntry] {
        let pinned = Set(store.pinnedTickers)
        return store.watchlist
            .filter { $0.last != nil }
            .sorted { a, b in
                let pa = pinned.contains(a.ticker), pb = pinned.contains(b.ticker)
                if pa != pb { return pa }
                return a.ticker < b.ticker
            }
            .map(MacTapeEntry.init)
    }

    var body: some View {
        let items = entries
        let desk = store
        Group {
            if items.isEmpty {
                Text("Ticker tape — pin tickers on Market Radar to fill it")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
            } else if reduceMotion {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: MacTapeLayout.spacing) {
                        ForEach(items) { entry in
                            MacTapeItemLabel(entry: entry)
                                .contentShape(Rectangle())
                                .onTapGesture { desk.showTicker(entry.ticker) }
                                .help(entry.name ?? entry.ticker)
                        }
                    }
                    .padding(.horizontal, 12)
                }
            } else {
                MacTapeMarquee(entries: items, speed: speed) { desk.showTicker($0) }
            }
        }
        .frame(height: 28)
        .background(Color(nsColor: .controlBackgroundColor))
        .overlay(alignment: .bottom) { Divider() }
        .clipped()
        .accessibilityLabel("Ticker tape")
    }
}

private struct MacTapeEntry: Identifiable, Hashable {
    let ticker: String
    let price: String
    let change: String
    let isUp: Bool
    let name: String?
    var id: String { ticker }

    init(_ quote: MacQuote) {
        ticker = quote.ticker
        price = quote.priceText
        change = quote.pctText
        isUp = quote.isUp
        name = quote.name
    }
}

private struct MacTapeItemLabel: View {
    let entry: MacTapeEntry

    var body: some View {
        HStack(spacing: 6) {
            Text(entry.ticker)
                .font(.caption.monospacedDigit().weight(.bold))
            Text(entry.price)
                .font(.caption.monospacedDigit())
            Text(entry.change)
                .font(.caption.monospacedDigit().weight(.semibold))
                .foregroundStyle(entry.isUp ? Color.green : Color.red)
        }
        .fixedSize()
    }
}

/// One copy of the strip is `period` points wide (items, spacing and the trailing gap);
/// `copies` repeats it so a translation of up to one period always covers the tape.
private struct MacTapeLayout: Equatable {
    static let spacing: CGFloat = 22
    static let gap: CGFloat = 40

    let entries: [MacTapeEntry]
    let widths: [CGFloat]
    let copies: Int

    var period: CGFloat {
        widths.reduce(0, +) + Self.spacing * CGFloat(max(widths.count - 1, 0)) + Self.gap
    }

    var totalWidth: CGFloat { period * CGFloat(copies) }

    static func copies(covering span: CGFloat, period: CGFloat) -> Int {
        guard period > 0 else { return 1 }
        return Int((span / period).rounded(.up)) + 1
    }

    func entryIndex(atStripX x: CGFloat) -> Int? {
        let period = period
        guard period > 0 else { return nil }
        var local = x.truncatingRemainder(dividingBy: period)
        if local < 0 { local += period }
        var start: CGFloat = 0
        for (index, width) in widths.enumerated() {
            if local >= start - Self.spacing / 2, local < start + width + Self.spacing / 2 { return index }
            start += width + Self.spacing
        }
        return nil
    }
}

private struct MacTapeMarqueeStrip: View {
    let layout: MacTapeLayout
    let onSelect: (String) -> Void

    var body: some View {
        HStack(spacing: 0) {
            ForEach(0..<layout.copies, id: \.self) { copy in
                HStack(spacing: 0) {
                    ForEach(Array(layout.entries.enumerated()), id: \.offset) { index, entry in
                        MacTapeItemLabel(entry: entry)
                            .frame(width: layout.widths[index], alignment: .leading)
                            .padding(.trailing, index == layout.entries.count - 1 ? MacTapeLayout.gap : MacTapeLayout.spacing)
                            .accessibilityElement(children: .combine)
                            .accessibilityAddTraits(.isButton)
                            .accessibilityAction { onSelect(entry.ticker) }
                    }
                }
                .accessibilityHidden(copy > 0)
            }
        }
        .frame(width: layout.totalWidth, alignment: .leading)
    }
}

private struct MacTapeMarquee: NSViewRepresentable {
    let entries: [MacTapeEntry]
    let speed: CGFloat
    let onSelect: (String) -> Void

    func makeNSView(context: Context) -> MacTapeMarqueeView {
        let view = MacTapeMarqueeView()
        view.onSelect = onSelect
        view.update(entries: entries, speed: speed)
        return view
    }

    func updateNSView(_ nsView: MacTapeMarqueeView, context: Context) {
        nsView.onSelect = onSelect
        nsView.update(entries: entries, speed: speed)
    }

    static func dismantleNSView(_ nsView: MacTapeMarqueeView, coordinator: ()) {
        nsView.stopScrolling()
    }
}

/// Hosts the pre-measured strip and scrolls it with one repeating `transform.translation.x`
/// animation. Hover pauses the layer clock; clicks and tooltips read the presentation layer.
private final class MacTapeMarqueeView: NSView {
    private static let animationKey = "tape.scroll"
    private static let leadingInset: CGFloat = 12

    var onSelect: ((String) -> Void)?

    private let scroller = NSView()
    private var host: NSHostingView<MacTapeMarqueeStrip>?
    private var measurer: NSHostingView<MacTapeItemLabel>?
    private var tapeLayout: MacTapeLayout?
    private var entries: [MacTapeEntry] = []
    private var speed: CGFloat = 0
    private var animatedPeriod: CGFloat = 0
    private var animatedSpeed: CGFloat = 0
    private var paused = false
    private var pressedTicker: String?
    private var widthRebuildPending = false
    private var tracking: NSTrackingArea?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        clipsToBounds = true
        scroller.wantsLayer = true
        addSubview(scroller)
    }

    required init?(coder: NSCoder) {
        return nil
    }

    func update(entries: [MacTapeEntry], speed: CGFloat) {
        guard entries != self.entries || speed != self.speed else { return }
        self.entries = entries
        self.speed = speed
        rebuild()
    }

    func stopScrolling() {
        guard let layer = scroller.layer else { return }
        layer.removeAnimation(forKey: Self.animationKey)
        layer.speed = 1
        layer.timeOffset = 0
        layer.beginTime = 0
        paused = false
        animatedPeriod = 0
    }

    private var coverageSpan: CGFloat {
        max(bounds.width, NSScreen.screens.map(\.frame.width).max() ?? 0)
    }

    private func rebuild() {
        let widths = entries.map(measure)
        let single = MacTapeLayout(entries: entries, widths: widths, copies: 1)
        let next = MacTapeLayout(
            entries: entries,
            widths: widths,
            copies: MacTapeLayout.copies(covering: coverageSpan, period: single.period)
        )
        if next != tapeLayout {
            let offset = currentOffset()
            tapeLayout = next
            let strip = MacTapeMarqueeStrip(layout: next) { [weak self] ticker in self?.onSelect?(ticker) }
            if let host {
                host.rootView = strip
            } else {
                let created = NSHostingView(rootView: strip)
                created.sizingOptions = []
                scroller.addSubview(created)
                host = created
            }
            placeStrip()
            if next.period != animatedPeriod || speed != animatedSpeed {
                startScrolling(from: offset)
            }
        }
        if scroller.layer?.animation(forKey: Self.animationKey) == nil {
            startScrolling(from: 0)
        }
    }

    private func measure(_ entry: MacTapeEntry) -> CGFloat {
        let label = MacTapeItemLabel(entry: entry)
        if let measurer {
            measurer.rootView = label
            return ceil(measurer.fittingSize.width)
        }
        let created = NSHostingView(rootView: label)
        measurer = created
        return ceil(created.fittingSize.width)
    }

    private func currentOffset() -> CGFloat {
        guard let layer = scroller.layer, layer.animation(forKey: Self.animationKey) != nil,
              let value = layer.presentation()?.value(forKeyPath: "transform.translation.x") as? NSNumber
        else { return 0 }
        return -CGFloat(value.doubleValue)
    }

    private func placeStrip() {
        guard let tapeLayout, let host else { return }
        let size = NSSize(width: tapeLayout.totalWidth, height: bounds.height)
        let frame = NSRect(origin: NSPoint(x: Self.leadingInset, y: 0), size: size)
        if scroller.frame != frame { scroller.frame = frame }
        let hostFrame = NSRect(origin: .zero, size: size)
        if host.frame != hostFrame { host.frame = hostFrame }
    }

    private func startScrolling(from offset: CGFloat) {
        guard let layer = scroller.layer else { return }
        layer.removeAnimation(forKey: Self.animationKey)
        animatedPeriod = 0
        guard window != nil, let tapeLayout, tapeLayout.period > 0, speed > 0 else { return }
        let period = tapeLayout.period
        let animation = CABasicAnimation(keyPath: "transform.translation.x")
        animation.fromValue = 0
        animation.toValue = -period
        animation.duration = CFTimeInterval(period / speed)
        animation.repeatCount = .infinity
        animation.isRemovedOnCompletion = false
        animation.timeOffset = CFTimeInterval(offset.truncatingRemainder(dividingBy: period) / speed)
        layer.add(animation, forKey: Self.animationKey)
        animatedPeriod = period
        animatedSpeed = speed
    }

    private func setPaused(_ pause: Bool) {
        guard let layer = scroller.layer, pause != paused else { return }
        paused = pause
        if pause {
            let now = layer.convertTime(CACurrentMediaTime(), from: nil)
            layer.speed = 0
            layer.timeOffset = now
        } else {
            let pausedAt = layer.timeOffset
            layer.speed = 1
            layer.timeOffset = 0
            layer.beginTime = 0
            layer.beginTime = layer.convertTime(CACurrentMediaTime(), from: nil) - pausedAt
        }
    }

    private func entry(at point: NSPoint) -> MacTapeEntry? {
        guard let tapeLayout, bounds.contains(point) else { return nil }
        let translation = (scroller.layer?.presentation()?.value(forKeyPath: "transform.translation.x") as? NSNumber)?.doubleValue ?? 0
        let stripX = point.x - scroller.frame.minX - CGFloat(translation)
        return tapeLayout.entryIndex(atStripX: stripX).map { tapeLayout.entries[$0] }
    }

    override func layout() {
        super.layout()
        placeStrip()
        guard let tapeLayout, !widthRebuildPending,
              MacTapeLayout.copies(covering: bounds.width, period: tapeLayout.period) > tapeLayout.copies
        else { return }
        widthRebuildPending = true
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.widthRebuildPending = false
            self.rebuild()
        }
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        if window == nil {
            stopScrolling()
        } else if scroller.layer?.animation(forKey: Self.animationKey) == nil {
            startScrolling(from: 0)
        }
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking { removeTrackingArea(tracking) }
        let area = NSTrackingArea(
            rect: .zero,
            options: [.mouseEnteredAndExited, .mouseMoved, .activeInActiveApp, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(area)
        tracking = area
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        guard !isHidden, let superview else { return nil }
        return bounds.contains(convert(point, from: superview)) ? self : nil
    }

    override func mouseEntered(with event: NSEvent) {
        setPaused(true)
    }

    override func mouseExited(with event: NSEvent) {
        setPaused(false)
        toolTip = nil
    }

    override func mouseMoved(with event: NSEvent) {
        let tip = entry(at: convert(event.locationInWindow, from: nil)).map { $0.name ?? $0.ticker }
        if toolTip != tip { toolTip = tip }
    }

    override func mouseDown(with event: NSEvent) {
        pressedTicker = entry(at: convert(event.locationInWindow, from: nil))?.ticker
    }

    override func mouseUp(with event: NSEvent) {
        defer { pressedTicker = nil }
        guard let ticker = entry(at: convert(event.locationInWindow, from: nil))?.ticker,
              ticker == pressedTicker else { return }
        onSelect?(ticker)
    }
}
