import SwiftUI

/// Ask mark — portrait of the selected legendary investor.
struct AskMark: View {
    @EnvironmentObject private var askPersona: AskPersonaStore
    var size: CGFloat = 40

    var body: some View {
        Image(askPersona.investor.imageName)
            .resizable()
            .scaledToFit()
            .frame(width: size, height: size, alignment: .center)
            .clipShape(Circle())
            .accessibilityHidden(true)
    }
}
