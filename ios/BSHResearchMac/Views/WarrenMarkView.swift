import SwiftUI

// MARK: - WarrenMarkView (Identical to WarrenMark.vue on the Website)

/// Warren's portrait: the Ask mark, identical to WarrenMark.vue and AskMark.swift.
/// Renders Warren Buffett's portrait with a hairline border, drop shadow,
/// and a breathing sky-light halo when busy.
struct WarrenMarkView: View {
    var size: CGFloat = 28
    var isBusy: Bool = false

    @State private var breathing: Bool = false

    var body: some View {
        ZStack {
            // Busy breathing ring: sky-light halo around the portrait
            if isBusy {
                Circle()
                    .stroke(
                        Color.accentColor.opacity(breathing ? 0.95 : 0.35),
                        lineWidth: max(1.2, size * 0.06)
                    )
                    .frame(width: size + max(4, size * 0.18), height: size + max(4, size * 0.18))
                    .shadow(color: Color.accentColor.opacity(0.5), radius: max(2, size * 0.15))
                    .scaleEffect(breathing ? 1.04 : 0.96)
                    .onAppear {
                        withAnimation(
                            Animation.easeInOut(duration: 1.8).repeatForever(autoreverses: true)
                        ) {
                            breathing = true
                        }
                    }
            }

            // Warren portrait from Assets with hairline border and soft drop shadow
            Image("AskMark")
                .renderingMode(.original)
                .resizable()
                .scaledToFill()
                .frame(width: size, height: size)
                .clipShape(Circle())
                .overlay(
                    Circle()
                        .stroke(Color.primary.opacity(0.14), lineWidth: 0.5)
                )
                .shadow(color: Color.black.opacity(0.10), radius: 1.5, x: 0, y: 1)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

// MARK: - AiOrbView (Identical to AiMark.vue / ai-orb.png)

/// Canonical AI Orb mark used on Generate Report buttons across web and desktop.
struct AiOrbView: View {
    var size: CGFloat = 14

    var body: some View {
        Image("AiOrb")
            .renderingMode(.original)
            .resizable()
            .interpolation(.high)
            .scaledToFit()
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}
