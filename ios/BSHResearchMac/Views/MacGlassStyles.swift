//
//  MacGlassStyles.swift
//  BSHResearchMac
//
//  Apple Glass & visionOS Liquid Glass Design System.
//  Provides translucent materials, specular hairline rim reflections,
//  multi-stop diffuse shadows, and ambient chromatic refraction.
//

import SwiftUI
import AppKit

// MARK: - Apple Glass Card Modifier
struct AppleGlassCardModifier: ViewModifier {
    var cornerRadius: CGFloat = 16
    var tint: Color? = nil
    var isInteractive: Bool = false

    @State private var isHovered: Bool = false

    func body(content: Content) -> some View {
        content
            .background(
                ZStack {
                    // 1. Frosted Ultra-Thin Material
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .fill(.ultraThinMaterial)

                    // 2. Liquid Refraction Gradient Tint (visionOS Glass Style)
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .fill(
                            LinearGradient(
                                colors: [
                                    (tint ?? Color.accentColor).opacity(isHovered ? 0.08 : 0.04),
                                    Color.purple.opacity(0.02),
                                    Color.clear
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                }
            )
            // 3. Specular Hairline Rim Reflection (Physical Glass Keylight)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(
                        LinearGradient(
                            stops: [
                                .init(color: .white.opacity(isHovered ? 0.50 : 0.35), location: 0.0),
                                .init(color: .white.opacity(0.12), location: 0.35),
                                .init(color: .clear, location: 0.70),
                                .init(color: .black.opacity(0.20), location: 1.0)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 1
                    )
            )
            // 4. Optical Dual-Stop Diffuse Shadows
            .shadow(color: Color.black.opacity(isHovered ? 0.16 : 0.11), radius: isHovered ? 20 : 14, x: 0, y: isHovered ? 8 : 5)
            .shadow(color: Color.black.opacity(0.04), radius: 3, x: 0, y: 1)
            .onHover { hovering in
                if isInteractive {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isHovered = hovering
                    }
                }
            }
    }
}

// MARK: - Apple Glass Tile (Inner Sub-Cards & Metric Cells)
struct AppleGlassTileModifier: ViewModifier {
    var cornerRadius: CGFloat = 10
    var tint: Color? = nil

    func body(content: Content) -> some View {
        content
            .background(
                ZStack {
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .fill(.thinMaterial)

                    if let tint = tint {
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .fill(tint.opacity(0.06))
                    }
                }
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(
                        LinearGradient(
                            stops: [
                                .init(color: .white.opacity(0.28), location: 0.0),
                                .init(color: .white.opacity(0.06), location: 0.40),
                                .init(color: .clear, location: 0.80)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 0.8
                    )
            )
    }
}

// MARK: - Apple Glass Pill (Badges, Chips, Compact Buttons)
struct AppleGlassPillModifier: ViewModifier {
    var color: Color = .accentColor

    func body(content: Content) -> some View {
        content
            .background(
                Capsule()
                    .fill(.ultraThinMaterial)
                    .overlay(Capsule().fill(color.opacity(0.12)))
            )
            .overlay(
                Capsule()
                    .stroke(
                        LinearGradient(
                            colors: [.white.opacity(0.35), .white.opacity(0.08)],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                        lineWidth: 0.8
                    )
            )
    }
}

// MARK: - Ambient Glass Background Canvas (Depth provider for Frosted Layers)
struct AmbientGlassCanvas<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        ZStack {
            // Ambient subtle multi-chroma fluid auras
            GeometryReader { proxy in
                ZStack {
                    Color(nsColor: .windowBackgroundColor)
                        .ignoresSafeArea()

                    // Top-Left Soft Indigo Glow
                    Circle()
                        .fill(Color.blue.opacity(0.07))
                        .blur(radius: 120)
                        .frame(width: proxy.size.width * 0.6, height: proxy.size.width * 0.6)
                        .offset(x: -proxy.size.width * 0.2, y: -proxy.size.height * 0.2)

                    // Bottom-Right Soft Purple Glow
                    Circle()
                        .fill(Color.purple.opacity(0.05))
                        .blur(radius: 140)
                        .frame(width: proxy.size.width * 0.7, height: proxy.size.width * 0.7)
                        .offset(x: proxy.size.width * 0.3, y: proxy.size.height * 0.3)

                    // Center-Right Subtle Cyan Shimmer
                    Circle()
                        .fill(Color.cyan.opacity(0.04))
                        .blur(radius: 100)
                        .frame(width: proxy.size.width * 0.4, height: proxy.size.width * 0.4)
                        .offset(x: proxy.size.width * 0.15, y: proxy.size.height * 0.05)
                }
            }
            .ignoresSafeArea()

            content()
        }
    }
}

// MARK: - View Extensions
extension View {
    func appleGlassCard(cornerRadius: CGFloat = 16, tint: Color? = nil, isInteractive: Bool = false) -> some View {
        modifier(AppleGlassCardModifier(cornerRadius: cornerRadius, tint: tint, isInteractive: isInteractive))
    }

    func appleGlassTile(cornerRadius: CGFloat = 10, tint: Color? = nil) -> some View {
        modifier(AppleGlassTileModifier(cornerRadius: cornerRadius, tint: tint))
    }

    func appleGlassPill(color: Color = .accentColor) -> some View {
        modifier(AppleGlassPillModifier(color: color))
    }

    func embeddedInAmbientGlass() -> some View {
        AmbientGlassCanvas { self }
    }
}
