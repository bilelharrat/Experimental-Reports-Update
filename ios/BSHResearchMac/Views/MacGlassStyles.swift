//
//  MacGlassStyles.swift
//  BSHResearchMac
//
//  Surface modifiers used by every desk. Names are kept from the first design pass;
//  the look is now flat macOS: white cards, hairline borders, quaternary tiles, no shadows.
//

import SwiftUI
#if canImport(AppKit)
import AppKit
#endif

struct AppleGlassCardModifier: ViewModifier {
    var cornerRadius: CGFloat = MacDS.cardRadius
    var tint: Color? = nil
    var isInteractive: Bool = false
    @State private var isHovered = false

    func body(content: Content) -> some View {
        let radius = min(cornerRadius, MacDS.cardRadius)
        content
            .background(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .fill(tint.map { $0.opacity(0.06) } ?? Color.clear)
                    .background(Color.dsCard, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            )
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .strokeBorder(isHovered ? Color.accentColor.opacity(0.35) : Color.dsHairline, lineWidth: 1)
            )
            .onHover { hovering in
                if isInteractive { withAnimation(.easeInOut(duration: 0.15)) { isHovered = hovering } }
            }
    }
}

struct AppleGlassTileModifier: ViewModifier {
    var cornerRadius: CGFloat = MacDS.tileRadius
    var tint: Color? = nil

    func body(content: Content) -> some View {
        content.background(
            RoundedRectangle(cornerRadius: min(cornerRadius, 10), style: .continuous)
                .fill(tint.map { $0.opacity(0.10) } ?? Color.dsTile)
        )
    }
}

struct AppleGlassPillModifier: ViewModifier {
    var color: Color = .accentColor
    func body(content: Content) -> some View {
        content.background(Capsule().fill(color.opacity(0.14)))
    }
}

/// The desk canvas: the plain window background, nothing painted behind the cards.
struct AmbientGlassCanvas<Content: View>: View {
    @ViewBuilder let content: () -> Content
    var body: some View {
        content().background(Color.dsCanvas.ignoresSafeArea())
    }
}

extension View {
    func appleGlassCard(cornerRadius: CGFloat = MacDS.cardRadius, tint: Color? = nil, isInteractive: Bool = false) -> some View {
        modifier(AppleGlassCardModifier(cornerRadius: cornerRadius, tint: tint, isInteractive: isInteractive))
    }

    func appleGlassTile(cornerRadius: CGFloat = MacDS.tileRadius, tint: Color? = nil) -> some View {
        modifier(AppleGlassTileModifier(cornerRadius: cornerRadius, tint: tint))
    }

    func appleGlassPill(color: Color = .accentColor) -> some View {
        modifier(AppleGlassPillModifier(color: color))
    }

    func embeddedInAmbientGlass() -> some View {
        AmbientGlassCanvas { self }
    }
}

// MARK: - Glass list selection

/// Liquid Glass highlight behind the selected row of a `List(selection:)`, replacing AppKit's
/// solid accent (gray under Graphite) fill. The List keeps its native selection, so arrow keys,
/// type-select and VoiceOver work unchanged; only the drawing moves to glass.
struct GlassRowHighlight: View {
    var isSelected: Bool
    var cornerRadius: CGFloat = 8
    var inset: EdgeInsets = EdgeInsets(top: 2, leading: 6, bottom: 2, trailing: 6)

    var body: some View {
        ZStack {
            if isSelected {
                LevitatingGlassPill(cornerRadius: cornerRadius)
                    .padding(inset)
                    .transition(.scale(scale: 0.94).combined(with: .opacity))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(NativeSelectionHighlightRemover())
        .animation(.spring(response: 0.32, dampingFraction: 0.72), value: isSelected)
    }
}

/// The glass pill itself, hovering over the row: a tight contact shadow plus a wide, soft
/// drop shadow. It springs up into the air on selection (its own view, so every new
/// selection replays the lift) and then holds still; no looping animation.
private struct LevitatingGlassPill: View {
    var cornerRadius: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var aloft = false

    var body: some View {
        GlassPillSurface(
            shape: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous),
            shadowRadius: aloft ? 10 : 6,
            shadowY: aloft ? 8 : 4,
            shadowOpacity: aloft ? 0.13 : 0.18
        )
        .scaleEffect(aloft ? 1 : 0.96)
        .onAppear {
            if reduceMotion { aloft = true; return }
            withAnimation(.spring(response: 0.42, dampingFraction: 0.55)) { aloft = true }
        }
    }
}

/// The levitating glass surface shared by list selection and the segmented control thumb:
/// Liquid Glass (material before macOS 26), a specular rim, a contact shadow and a drop shadow.
struct GlassPillSurface<S: InsettableShape>: View {
    var shape: S
    var shadowRadius: CGFloat = 10
    var shadowY: CGFloat = 8
    var shadowOpacity: Double = 0.13
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let dark = colorScheme == .dark
        glass
            .overlay(shape.strokeBorder(rim, lineWidth: 1))
            .shadow(color: .black.opacity(dark ? 0.30 : 0.06), radius: 1, y: 0.5)
            .shadow(color: .black.opacity(dark ? 0.50 : shadowOpacity), radius: shadowRadius, y: shadowY)
    }

    /// Specular rim: bright along the top edge, fading out toward the bottom.
    private var rim: LinearGradient {
        let dark = colorScheme == .dark
        return LinearGradient(
            colors: [Color.white.opacity(dark ? 0.30 : 0.95), Color.white.opacity(dark ? 0.06 : 0.35)],
            startPoint: .top, endPoint: .bottom
        )
    }

    @ViewBuilder
    private var glass: some View {
        let lift = Color.white.opacity(colorScheme == .dark ? 0.10 : 0.60)
        if #available(macOS 26.0, *) {
            shape.fill(Color.clear)
                .glassEffect(.regular.tint(lift), in: shape)
        } else {
            shape.fill(.regularMaterial)
                .overlay(shape.fill(lift))
        }
    }
}

// MARK: - Glass segmented control

/// Replaces `Picker` + `.pickerStyle(.segmented)`, whose selected segment AppKit paints in the
/// system accent (solid gray under Graphite). Equal-width segments on a soft track, with a
/// levitating glass thumb that slides to the chosen segment. Like the native control it fills
/// the width it is offered, so `.frame(width:)` and `.fixedSize()` size it the same way.
struct GlassSegmentedPicker<Value: Hashable>: View {
    struct Segment {
        let value: Value
        let title: String
        var systemImage: String? = nil
    }

    private let label: String
    @Binding private var selection: Value
    private let segments: [Segment]
    @Environment(\.controlSize) private var controlSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Namespace private var thumb
    @State private var hovered: Value?

    init(_ label: String, selection: Binding<Value>, segments: KeyValuePairs<Value, String>) {
        self.label = label
        self._selection = selection
        self.segments = segments.map { Segment(value: $0.key, title: $0.value) }
    }

    init(_ label: String, selection: Binding<Value>, options: [Value], title: (Value) -> String, systemImage: ((Value) -> String?)? = nil) {
        self.label = label
        self._selection = selection
        self.segments = options.map { Segment(value: $0, title: title($0), systemImage: systemImage?($0)) }
    }

    private var compact: Bool { controlSize == .small || controlSize == .mini }

    var body: some View {
        EqualWidthSegmentsLayout {
            ForEach(Array(segments.enumerated()), id: \.offset) { _, segment in
                segmentButton(segment)
            }
        }
        .padding(2)
        .background(Capsule(style: .continuous).fill(Color.primary.opacity(0.06)))
        .overlay(Capsule(style: .continuous).strokeBorder(Color.primary.opacity(0.07), lineWidth: 0.5))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(label)
    }

    private func segmentButton(_ segment: Segment) -> some View {
        let isSelected = segment.value == selection
        return Button {
            guard !isSelected else { return }
            if reduceMotion {
                selection = segment.value
            } else {
                withAnimation(.spring(response: 0.32, dampingFraction: 0.78)) { selection = segment.value }
            }
        } label: {
            HStack(spacing: 4) {
                if let systemImage = segment.systemImage {
                    Image(systemName: systemImage)
                }
                Text(segment.title)
            }
            .font(.system(size: compact ? 11 : 13, weight: .medium))
            .foregroundStyle(isSelected ? Color.primary : Color.primary.opacity(0.75))
            .lineLimit(1)
            .padding(.horizontal, compact ? 8 : 11)
            .padding(.vertical, compact ? 2 : 3.5)
            .frame(maxWidth: .infinity)
            .background {
                if isSelected {
                    GlassPillSurface(shape: Capsule(style: .continuous), shadowRadius: 4, shadowY: 2, shadowOpacity: 0.16)
                        .matchedGeometryEffect(id: "thumb", in: thumb)
                } else if hovered == segment.value {
                    Capsule(style: .continuous).fill(Color.primary.opacity(0.05))
                }
            }
            .contentShape(Capsule(style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { inside in
            if inside { hovered = segment.value } else if hovered == segment.value { hovered = nil }
        }
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

/// Lays segments out side by side at equal widths: the widest segment's ideal width times the
/// count when unconstrained, otherwise exactly the offered width.
private struct EqualWidthSegmentsLayout: Layout {
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        let ideals = subviews.map { $0.sizeThatFits(.unspecified) }
        let ideal = (ideals.map(\.width).max() ?? 0) * CGFloat(subviews.count)
        let height = ideals.map(\.height).max() ?? 0
        let width = proposal.width.flatMap { $0.isFinite ? $0 : nil } ?? ideal
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let width = bounds.width / CGFloat(subviews.count)
        for (index, subview) in subviews.enumerated() {
            subview.place(
                at: CGPoint(x: bounds.minX + CGFloat(index) * width, y: bounds.midY),
                anchor: .leading,
                proposal: ProposedViewSize(width: width, height: bounds.height)
            )
        }
    }
}

#if os(macOS)
private struct NativeSelectionHighlightRemover: NSViewRepresentable {
    func makeNSView(context: Context) -> Probe { Probe() }
    func updateNSView(_ nsView: Probe, context: Context) {}

    final class Probe: NSView {
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard window != nil else { return }
            apply()
        }

        private func apply() {
            var view = superview
            while let current = view {
                // Let the levitating pill's shadow spill past the row instead of being cut flat.
                if current.clipsToBounds { current.clipsToBounds = false }
                if let rowView = current as? NSTableRowView {
                    if rowView.selectionHighlightStyle != .none { rowView.selectionHighlightStyle = .none }
                    return
                }
                view = current.superview
            }
        }

        override func hitTest(_ point: NSPoint) -> NSView? { nil }
    }
}
#else
private struct NativeSelectionHighlightRemover: View {
    var body: some View {
        Color.clear
    }
}
#endif

extension View {
    /// Row modifier for `List(selection:)`: draws the Liquid Glass highlight when `isSelected`.
    func glassListRow(isSelected: Bool, cornerRadius: CGFloat = 8) -> some View {
        listRowBackground(GlassRowHighlight(isSelected: isSelected, cornerRadius: cornerRadius))
    }
}
