//
//  MacBureauDecisionSheet.swift
//  BSHResearchMac
//
//  ⌘D under Bureau, drawn as the website draws it (RecordDecisionModal.vue, the `.mac-*`
//  controls in style.css and their Bureau overrides in bureau.css): a 520pt card on the page's
//  own paper with a hairline round it, laid over a light scrim that covers the whole window.
//  The header and footer are the card's paper; in between, one tray holds the verdict, the
//  day and the memo, and the rationale is fresh paper below it.
//
//  The sheet window is made as large as the window it hangs on, and clear, so the scrim and
//  the card sit where the website puts them. The form's state and what Record does stay in
//  MacDecisionSheet.
//

import AppKit
import SwiftUI

struct MacBureauDecisionSheet: View {
    let company: MacCompany
    @Binding var verdict: String
    @Binding var explanation: String
    @Binding var decidedAt: Date
    @Binding var reportId: String
    let reports: [MacReport]
    let submitting: Bool
    let error: String?
    let recordedAs: String
    let submit: () -> Void
    let cancel: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    /// The window the sheet hangs on; the scrim covers all of it.
    @State private var host = MacBureauSheetHost.parentSizeGuess()
    /// The rationale's height: 140 by default, taller by hand (the website's `resize-y`).
    @State private var rationaleHeight: CGFloat = 140
    @State private var cardHeight: CGFloat = 433.36

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var canSubmit: Bool {
        !submitting && !explanation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var verdictTitle: String {
        switch verdict {
        case "invest": return "Invest"
        case "pass": return "Pass"
        default: return "Watch"
        }
    }

    var body: some View {
        // The website's dialog box is the desk's height (the window less the masthead and the
        // gutter under the sheet), from the top: the card is centred in that.
        let left = ((host.width - 520) / 2).rounded(.down)
        let top = max(16, (host.height - 62 - cardHeight) / 2)
        ZStack(alignment: .topLeading) {
            Color.black.opacity(0.28)
                .contentShape(Rectangle())
            card
                .frame(width: 520)
                .fixedSize(horizontal: false, vertical: true)
                .background {
                    GeometryReader { geo in
                        Color.clear
                            .onAppear { cardHeight = geo.size.height }
                            .onChange(of: geo.size.height) { _, height in cardHeight = height }
                    }
                }
                .offset(x: left, y: top)
        }
        .frame(width: host.width, height: host.height, alignment: .topLeading)
        .background(MacBureauSheetHost(parentSize: $host))
        .presentationBackground(.clear)
        .font(BSHType.bureauSans(13))
    }

    // MARK: The card

    private var card: some View {
        VStack(spacing: 0) {
            header
            rule
            form
            rule
            footer
        }
        .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(ink.sheet))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .circular))
        // 0 0 0 1px var(--mac-hairline): the hairline just outside the paper.
        .background {
            RoundedRectangle(cornerRadius: 12, style: .circular)
                .inset(by: -0.5)
                .stroke(ink.rule, lineWidth: 1)
        }
        // 0 24px 60px rgba(0, 0, 0, 0.35)
        .background {
            RoundedRectangle(cornerRadius: 12, style: .circular)
                .fill(Color.black.opacity(0.35))
                .offset(y: 24)
                .blur(radius: 30)
                .allowsHitTesting(false)
        }
    }

    private var rule: some View {
        Rectangle().fill(ink.rule).frame(height: 1)
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .center, spacing: 0) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Record Decision")
                    .font(BSHType.bureauSans(13, weight: .semibold))
                    .foregroundStyle(ink.ink)
                    .bureauLines(16.9, size: 13)
                Text(company.title)
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauLines(13.75, size: 11)
            }
            Spacer(minLength: 0)
            MacBureauDecisionPill("Cancel", action: cancel)
                .keyboardShortcut(.cancelAction)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    // MARK: Form

    private var form: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(spacing: 0) {
                row("Verdict") {
                    MacBureauVerdictSegments(selection: $verdict)
                }
                .padding(.vertical, 8)
                tileRule
                row("Decided") {
                    MacBureauDecisionDateField(date: $decidedAt)
                }
                .padding(.vertical, 8)
                tileRule
                row("Based on memo") {
                    memoPopup
                }
                .padding(.vertical, 8)
            }
            .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(ink.fillTertiary))

            VStack(alignment: .leading, spacing: 6) {
                Text("Rationale (required — this is the firm's record)")
                    .font(BSHType.bureauSans(11, weight: .medium))
                    .foregroundStyle(ink.muted)
                    .bureauLines(13.75, size: 11)
                MacBureauRationaleField(text: $explanation, height: $rationaleHeight)
            }

            if let error {
                Text(error)
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.danger)
                    .bureauLines(13.75, size: 11)
            }
        }
        .padding(16)
    }

    private var tileRule: some View {
        Rectangle().fill(ink.rule).frame(height: 1).padding(.horizontal, 10)
    }

    private func row<Control: View>(_ label: String, @ViewBuilder control: () -> Control) -> some View {
        HStack(alignment: .center, spacing: 16) {
            Text(label)
                .foregroundStyle(ink.ink)
                .bureauLines(17.55, size: 13)
                .fixedSize()
            Spacer(minLength: 0)
            control()
        }
        .padding(.horizontal, 10)
    }

    /// `.mac-popup`: a small pill ruled in ink holding the memo's name, a menu of the memos.
    private var memoPopup: some View {
        let chosen = reports.first { $0.id == reportId }
        return Menu {
            Button("None") { reportId = "" }
            ForEach(reports) { report in
                Button("\(report.displayTitle) · \(report.dateLabel)") { reportId = report.id }
            }
        } label: {
            MacBureauPopupFace(title: chosen.map { "\($0.displayTitle) · \($0.dateLabel)" } ?? "None")
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .frame(maxWidth: 280, alignment: .trailing)
    }

    // MARK: Footer

    private var footer: some View {
        HStack(alignment: .center, spacing: 0) {
            Text("Recorded as \(recordedAs)")
                .font(BSHType.bureauSans(10))
                .foregroundStyle(ink.muted)
                .bureauLines(12.5, size: 10)
            Spacer(minLength: 0)
            MacBureauDecisionPill(submitting ? "Saving…" : "Record \(verdictTitle)", prominent: true, action: submit)
                .keyboardShortcut(.defaultAction)
                .disabled(!canSubmit)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }
}

// MARK: - Controls

/// `.mac-btn` under Bureau: a 13pt pill ruled in ink; prominent, brass with light across its
/// top. Disabled, it fades to 45%.
private struct MacBureauDecisionPill: View {
    let title: String
    var prominent = false
    let action: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @State private var hovered = false

    init(_ title: String, prominent: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.prominent = prominent
        self.action = action
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            Text(title)
                .font(BSHType.bureauSans(13, weight: .medium))
                .lineLimit(1)
                .fixedSize()
                .bureauLines(15.6, size: 13)
                .foregroundStyle(prominent ? Color.bshFixed(BSHRGB(255, 253, 246)) : ink.ink)
                .padding(.horizontal, 12)
                .padding(.vertical, 4.5)
                .background { face(ink) }
                .contentShape(Capsule())
        }
        .buttonStyle(MacBureauDecisionPillPress())
        .onHover { hovered = $0 }
        .opacity(isEnabled ? 1 : 0.45)
    }

    @ViewBuilder
    private func face(_ ink: MacBureauPageInk) -> some View {
        if prominent {
            Capsule()
                .fill(hovered && isEnabled ? ink.accentHover : ink.accent)
                .overlay(Capsule().fill(LinearGradient(
                    stops: [.init(color: .white.opacity(0.16), location: 0), .init(color: .white.opacity(0), location: 0.6)],
                    startPoint: .top, endPoint: .bottom
                )))
                // inset 0 1px 0 rgb(255 255 255 / 0.22): light along the top edge.
                .overlay(
                    ZStack {
                        Capsule().fill(Color.white.opacity(0.22))
                        Capsule().fill(Color.black).offset(y: 1).blendMode(.destinationOut)
                    }
                    .compositingGroup()
                    .clipShape(Capsule())
                )
                // 0 0 0 1px rgb(var(--color-accent-hover) / 0.55)
                .background(Capsule().inset(by: -0.5).stroke(ink.accentHover.opacity(0.55), lineWidth: 1))
        } else {
            Capsule()
                .fill(hovered && isEnabled ? ink.ink(0.05) : .clear)
                .overlay(Capsule().strokeBorder(ink.ink(0.2), lineWidth: 1))
        }
    }
}

/// `.mac-btn:active`: pressed, the pill darkens a little.
private struct MacBureauDecisionPillPress: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.brightness(configuration.isPressed ? -0.06 : 0)
    }
}

/// `.mac-popup select`: the chosen memo in a small pill ruled in ink.
private struct MacBureauPopupFace: View {
    let title: String
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Text(title)
            .font(BSHType.bureauSans(11, weight: .medium))
            .foregroundStyle(ink.ink)
            .lineLimit(1)
            .truncationMode(.tail)
            .bureauLines(13.2, size: 11)
            .padding(.leading, 9)
            .padding(.trailing, 20)
            .padding(.vertical, 3)
            .background(Capsule().fill(hovered ? ink.ink(0.05) : .clear))
            .overlay(Capsule().strokeBorder(ink.ink(0.2), lineWidth: 1))
            .contentShape(Capsule())
            .onHover { hovered = $0 }
    }
}

/// `.mac-segmented` under Bureau: Invest, Watch and Pass in a groove pressed into the tray;
/// the chosen one a slip of fresh paper lifted from it.
private struct MacBureauVerdictSegments: View {
    @Binding var selection: String
    @Environment(\.colorScheme) private var colorScheme
    @Namespace private var slip
    @State private var hovered: String?

    private static let options: [(value: String, title: String, icon: String)] = [
        ("invest", "Invest", "circle-check"),
        ("watch", "Watch", "eye"),
        ("pass", "Pass", "circle-x"),
    ]

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 0) {
            ForEach(Self.options, id: \.value) { option in
                let chosen = option.value == selection
                Button {
                    guard !chosen else { return }
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.82)) { selection = option.value }
                } label: {
                    HStack(spacing: 4) {
                        LucideIcon(option.icon, size: 12)
                        Text(option.title)
                            .font(BSHType.bureauSans(11, weight: .medium))
                            .fixedSize()
                            .bureauLines(13.2, size: 11)
                    }
                    .foregroundStyle(chosen ? ink.ink : ink.ink(0.75))
                    .padding(.vertical, 2)
                    .frame(maxWidth: .infinity)
                    .background {
                        if chosen {
                            Capsule()
                                .fill(ink.raised)
                                // 0 0 0 1px ink/0.08, 0 1px 3px shadow/0.14
                                .background(Capsule().inset(by: -0.5).stroke(ink.ink(0.08), lineWidth: 1))
                                .shadow(color: ink.shadow(0.14), radius: 1.5, y: 1)
                                .matchedGeometryEffect(id: "slip", in: slip)
                        } else if hovered == option.value {
                            Capsule().fill(ink.ink(0.05))
                        }
                    }
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .onHover { inside in
                    if inside { hovered = option.value } else if hovered == option.value { hovered = nil }
                }
                .accessibilityLabel(option.title)
                .accessibilityAddTraits(chosen ? .isSelected : [])
            }
        }
        .padding(2)
        .frame(width: 280)
        .background {
            Capsule()
                .fill(ink.ink(0.06))
                .overlay(MacBureauInsetShadow(color: ink.shadow(0.06), blur: 2, y: 1, shape: Capsule()))
        }
    }
}

/// The decided day as the website's date field shows it (`.mac-field`, 12pt, figures in
/// step): the date in the reader's order and the calendar button, which opens a month to
/// pick from.
private struct MacBureauDecisionDateField: View {
    @Binding var date: Date
    @Environment(\.colorScheme) private var colorScheme
    @State private var picking = false

    private static let formatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.setLocalizedDateFormatFromTemplate("MMddyyyy")
        return formatter
    }()

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button {
            picking.toggle()
        } label: {
            HStack(spacing: 0) {
                MacBureauDateDigits(text: Self.formatter.string(from: date))
                Spacer(minLength: 0)
                MacBureauCalendarGlyph()
                    .foregroundStyle(ink.ink)
                    .frame(width: 16, height: 16)
            }
            .foregroundStyle(ink.ink)
            .padding(.leading, 8)
            .padding(.trailing, 7)
            .frame(width: 129, height: 28)
            .background(RoundedRectangle(cornerRadius: 7, style: .circular).fill(ink.raised))
            .contentShape(RoundedRectangle(cornerRadius: 7))
        }
        .buttonStyle(.plain)
        .popover(isPresented: $picking, arrowEdge: .bottom) {
            DatePicker("Decided", selection: $date, displayedComponents: .date)
                .datePickerStyle(.graphical)
                .labelsHidden()
                .padding(12)
        }
        .accessibilityLabel("Decided")
        .accessibilityValue(Self.formatter.string(from: date))
    }
}

/// A date as the browser's date field sets it: each figure group apart, the separators with
/// a little air on either side.
private struct MacBureauDateDigits: View {
    let text: String

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(parts.enumerated()), id: \.offset) { _, part in
                Text(part.text)
                    .font(BSHType.bureauSans(12).monospacedDigit())
                    .padding(.horizontal, part.isSeparator ? 0 : 1)
                    .fixedSize()
            }
        }
        .bureauLines(18, size: 12)
    }

    private var parts: [(text: String, isSeparator: Bool)] {
        var out: [(String, Bool)] = []
        var run = ""
        var runIsDigits = true
        for character in text {
            let digit = character.isNumber
            if run.isEmpty {
                runIsDigits = digit
            } else if digit != runIsDigits {
                out.append((run, !runIsDigits))
                run = ""
                runIsDigits = digit
            }
            run.append(character)
        }
        if !run.isEmpty { out.append((run, !runIsDigits)) }
        return out
    }
}

/// The browser's calendar button (Chrome's date picker indicator): a page of the calendar
/// with its top band filled.
private struct MacBureauCalendarGlyph: View {
    var body: some View {
        Canvas { context, size in
            // Drawn on Chrome's 24pt grid (Material's calendar_today), scaled to the frame.
            let s = min(size.width, size.height) / 24
            var outline = Path()
            outline.addRoundedRect(in: CGRect(x: 3 * s, y: 4 * s, width: 18 * s, height: 17 * s), cornerSize: CGSize(width: 2 * s, height: 2 * s))
            outline.addRect(CGRect(x: 5 * s, y: 10 * s, width: 14 * s, height: 9 * s))
            context.fill(outline, with: .foreground, style: FillStyle(eoFill: true))
            context.fill(Path(CGRect(x: 7 * s, y: 2 * s, width: 2 * s, height: 3 * s)), with: .foreground)
            context.fill(Path(CGRect(x: 15 * s, y: 2 * s, width: 2 * s, height: 3 * s)), with: .foreground)
        }
        .accessibilityHidden(true)
    }
}

/// The rationale: fresh paper, 13pt on an 18.2pt line, its placeholder in the subtle ink;
/// its lower corner drags it taller, as the browser's resize grip does.
private struct MacBureauRationaleField: View {
    @Binding var text: String
    @Binding var height: CGFloat
    @Environment(\.colorScheme) private var colorScheme
    @State private var dragStart: CGFloat?

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        ZStack(alignment: .topLeading) {
            if text.isEmpty {
                Text("Document thesis conviction, primary concerns, valuation discipline, and key conditions...")
                    .font(BSHType.bureauSans(13))
                    .foregroundStyle(ink.subtle)
                    .lineSpacing(18.2 - 16)
                    .bureauLines(18.2, size: 13)
                    .padding(.horizontal, 8)
                    .padding(.top, 4)
                    .allowsHitTesting(false)
            }
            TextEditor(text: $text)
                .font(BSHType.bureauSans(13))
                .foregroundStyle(ink.ink)
                .lineSpacing(18.2 - 16)
                .scrollContentBackground(.hidden)
                .scrollIndicators(.never)
                // NSTextView keeps 5pt of padding inside each line; the website's is 8.
                .padding(.horizontal, 3)
                .padding(.top, 4 + 1.1)
                .padding(.bottom, 4)
        }
        .frame(maxWidth: .infinity)
        .frame(height: height)
        .background(RoundedRectangle(cornerRadius: 7, style: .circular).fill(ink.raised))
        .overlay(alignment: .bottomTrailing) {
            MacBureauResizeGrip()
                .foregroundStyle(ink.ink(0.45))
                .frame(width: 12, height: 12)
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 1)
                        .onChanged { value in
                            let base = dragStart ?? height
                            if dragStart == nil { dragStart = height }
                            height = min(420, max(140, base + value.translation.height))
                        }
                        .onEnded { _ in dragStart = nil }
                )
                .onHover { inside in
                    if inside { NSCursor.resizeUpDown.push() } else { NSCursor.pop() }
                }
                .padding(.trailing, 2)
                .padding(.bottom, 2)
        }
    }
}

/// The browser's textarea grip: two short strokes across the lower corner.
private struct MacBureauResizeGrip: View {
    var body: some View {
        Canvas { context, size in
            var path = Path()
            path.move(to: CGPoint(x: size.width - 1, y: size.height - 8))
            path.addLine(to: CGPoint(x: size.width - 8, y: size.height - 1))
            path.move(to: CGPoint(x: size.width - 1, y: size.height - 4))
            path.addLine(to: CGPoint(x: size.width - 4, y: size.height - 1))
            context.stroke(path, with: .foreground, style: StrokeStyle(lineWidth: 1, lineCap: .round))
        }
        .accessibilityHidden(true)
    }
}

// MARK: - The sheet's window

/// Makes the sheet's window clear and as large as the window it hangs on, and keeps it so
/// when that window is resized, so the scrim covers the whole window as the website's does.
struct MacBureauSheetHost: NSViewRepresentable {
    @Binding var parentSize: CGSize

    /// The window the sheet is about to hang on is still the key window.
    static func parentSizeGuess() -> CGSize {
        if let window = NSApp.keyWindow ?? NSApp.mainWindow, window.sheetParent == nil {
            return window.frame.size
        }
        return CGSize(width: 1280, height: 820)
    }

    func makeNSView(context: Context) -> Probe {
        let probe = Probe()
        probe.onParent = { size in
            if parentSize != size { parentSize = size }
        }
        return probe
    }

    func updateNSView(_ nsView: Probe, context: Context) {
        nsView.onParent = { size in
            if parentSize != size { parentSize = size }
        }
    }

    final class Probe: NSView {
        var onParent: ((CGSize) -> Void)?
        private var observer: NSObjectProtocol?

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard let window else { return }
            window.isOpaque = false
            window.backgroundColor = .clear
            window.hasShadow = false
            attach(to: window, tries: 12)
        }

        /// The sheet's parent is set once the sheet begins; look again until it is.
        private func attach(to window: NSWindow, tries: Int) {
            if let parent = window.sheetParent {
                onParent?(parent.frame.size)
                if let observer { NotificationCenter.default.removeObserver(observer) }
                observer = NotificationCenter.default.addObserver(
                    forName: NSWindow.didResizeNotification, object: parent, queue: .main
                ) { [weak self] _ in
                    self?.onParent?(parent.frame.size)
                }
            } else if tries > 0 {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self, weak window] in
                    guard let self, let window else { return }
                    self.attach(to: window, tries: tries - 1)
                }
            }
        }

        deinit {
            if let observer { NotificationCenter.default.removeObserver(observer) }
        }
    }
}
