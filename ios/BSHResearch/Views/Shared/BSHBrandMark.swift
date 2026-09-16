//
//  BSHBrandMark.swift
//  BSHResearch
//
//  Berkeley Summit House company logo and brand mark components.
//  The vector geometry matches frontend/src/assets/berkeley-summit-house-mark.svg (viewBox="0 0 101 65").
//

import SwiftUI

/// Pure vector shape of the Berkeley Summit House twin-peak company mark.
public struct BSHBrandMarkShape: Shape {
    public init() {}

    public func path(in rect: CGRect) -> Path {
        let sx = rect.width / 101.0
        let sy = rect.height / 65.0
        let scale = min(sx, sy)
        let ox = rect.minX + (rect.width - 101.0 * scale) / 2.0
        let oy = rect.minY + (rect.height - 65.0 * scale) / 2.0

        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: ox + x * scale, y: oy + y * scale)
        }

        var path = Path()

        // Peak 1 (Primary / Right Summit)
        path.move(to: p(54.2302, 10.179))
        path.addLine(to: p(73.2761, 44.8541))
        path.addCurve(
            to: p(76.8381, 45.8573),
            control1: p(73.974, 46.119),
            control2: p(75.5732, 46.5843)
        )
        path.addLine(to: p(89.6323, 38.5733))
        path.addCurve(
            to: p(93.3688, 39.9836),
            control1: p(91.0426, 37.7737),
            control2: p(92.8309, 38.4425)
        )
        path.addLine(to: p(100.609, 60.876))
        path.addCurve(
            to: p(98.1521, 64.3217),
            control1: p(101.191, 62.5625),
            control2: p(99.9404, 64.3217)
        )
        path.addLine(to: p(38.9499, 64.3217))
        path.addCurve(
            to: p(36.4346, 61.0795),
            control1: p(37.2488, 64.3217),
            control2: p(36.013, 62.7224)
        )
        path.addLine(to: p(49.4469, 10.7751))
        path.addCurve(
            to: p(54.2302, 10.179),
            control1: p(50.0285, 8.49246),
            control2: p(53.1107, 8.11445)
        )
        path.closeSubpath()

        // Peak 2 (Secondary / Left Summit)
        path.move(to: p(36.202, 40.3179))
        path.addLine(to: p(29.0925, 62.5333))
        path.addCurve(
            to: p(26.6209, 64.3361),
            control1: p(28.7436, 63.6091),
            control2: p(27.755, 64.3361)
        )
        path.addLine(to: p(3.48961, 64.3361))
        path.addCurve(
            to: p(1.94849, 59.6546),
            control1: p(0.974389, 64.3361),
            control2: p(-0.0724086, 61.1375)
        )
        path.addLine(to: p(32.1893, 37.4392))
        path.addCurve(
            to: p(36.202, 40.3179),
            control1: p(34.2102, 35.9562),
            control2: p(36.9726, 37.9335)
        )
        path.closeSubpath()

        return path
    }
}

/// Standalone vector mark view with customizable size and tint.
public struct BSHBrandMark: View {
    public var width: CGFloat = 38
    public var color: Color = .primary

    public init(width: CGFloat = 38, color: Color = .primary) {
        self.width = width
        self.color = color
    }

    private var height: CGFloat {
        round(width * (65.0 / 101.0))
    }

    public var body: some View {
        BSHBrandMarkShape()
            .fill(color)
            .frame(width: width, height: height)
    }
}

/// High-gloss Apple dock-style brand tile with specular glass rim,
/// subtle ambient glow, and the Berkeley Summit House company logo.
public struct BSHBrandTile: View {
    public var size: CGFloat = 76
    public var cornerRadius: CGFloat = 18

    @Environment(\.colorScheme) private var colorScheme

    public init(size: CGFloat = 76, cornerRadius: CGFloat = 18) {
        self.size = size
        self.cornerRadius = cornerRadius
    }

    private var markWidth: CGFloat {
        round(size * 0.52)
    }

    public var body: some View {
        let isDark = colorScheme == .dark

        ZStack {
            // Ambient blue/sky halo behind tile
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(Color.accentColor.opacity(isDark ? 0.35 : 0.22))
                .blur(radius: 14)
                .offset(y: 4)

            // Primary glass slab
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: isDark
                            ? [
                                Color(red: 0.22, green: 0.23, blue: 0.27).opacity(0.95),
                                Color(red: 0.13, green: 0.14, blue: 0.17).opacity(0.95)
                              ]
                            : [
                                Color.white.opacity(0.98),
                                Color(red: 0.93, green: 0.94, blue: 0.97).opacity(0.95)
                              ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )

            // Inner diffuse glass material
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(.ultraThinMaterial.opacity(isDark ? 0.4 : 0.6))

            // Specular top highlight & hairline rim
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .strokeBorder(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(isDark ? 0.45 : 0.95),
                            Color.white.opacity(isDark ? 0.08 : 0.35),
                            Color.primary.opacity(isDark ? 0.04 : 0.06)
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    ),
                    lineWidth: 1
                )

            // The Company Logo Mark
            BSHBrandMarkShape()
                .fill(
                    LinearGradient(
                        colors: isDark
                            ? [Color.white, Color(white: 0.88)]
                            : [Color(red: 0.08, green: 0.09, blue: 0.12), Color(red: 0.18, green: 0.20, blue: 0.26)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: markWidth, height: round(markWidth * (65.0 / 101.0)))
                .shadow(
                    color: isDark ? Color.black.opacity(0.5) : Color.accentColor.opacity(0.18),
                    radius: isDark ? 3 : 2,
                    y: 1
                )
        }
        .frame(width: size, height: size)
        .shadow(
            color: Color.black.opacity(isDark ? 0.45 : 0.12),
            radius: 12,
            x: 0,
            y: 6
        )
    }
}
