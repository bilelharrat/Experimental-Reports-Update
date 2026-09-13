import SwiftUI
import UIKit

/// Tab-bar ECG mark matching `waveform.path.ecg`, with the S-valley raised ~25%
/// (shallower drop) so the trough sits higher than the SF Symbol.
struct PulseECGShape: Shape {
    func path(in rect: CGRect) -> Path {
        let w = rect.width
        let h = rect.height
        func pt(_ nx: CGFloat, _ ny: CGFloat) -> CGPoint {
            CGPoint(x: rect.minX + nx * w, y: rect.minY + ny * h)
        }

        // Normalized Y: 0 = top, 1 = bottom. Baseline mid-icon.
        // Standard SF-like S trough ≈ 0.94; raise by 25% of drop depth.
        let baseline: CGFloat = 0.50
        let deepValley: CGFloat = 0.94
        let valley = baseline + (deepValley - baseline) * 0.75

        var path = Path()
        path.move(to: pt(0.00, baseline))
        path.addLine(to: pt(0.14, baseline))
        // P
        path.addLine(to: pt(0.20, 0.36))
        path.addLine(to: pt(0.26, baseline))
        // Q
        path.addLine(to: pt(0.30, 0.58))
        // R peak
        path.addLine(to: pt(0.38, 0.06))
        // S valley (raised)
        path.addLine(to: pt(0.46, valley))
        path.addLine(to: pt(0.52, baseline))
        // T
        path.addLine(to: pt(0.60, 0.30))
        path.addLine(to: pt(0.70, baseline))
        path.addLine(to: pt(1.00, baseline))
        return path
    }
}

enum PulseECGTabIcon {
    /// Template image sized for tab-bar optical weight (~SF Symbol 25pt).
    static let image: UIImage = makeImage(pointSize: 25)

    static func makeImage(pointSize: CGFloat) -> UIImage {
        let size = CGSize(width: pointSize, height: pointSize)
        let format = UIGraphicsImageRendererFormat.default()
        format.opaque = false
        format.scale = 3
        let renderer = UIGraphicsImageRenderer(size: size, format: format)
        let image = renderer.image { ctx in
            let inset = CGRect(origin: .zero, size: size).insetBy(dx: 1.5, dy: 4.5)
            let path = PulseECGShape().path(in: inset)
            let cg = ctx.cgContext
            cg.setStrokeColor(UIColor.black.cgColor)
            cg.setLineWidth(1.85)
            cg.setLineCap(.round)
            cg.setLineJoin(.round)
            cg.addPath(path.cgPath)
            cg.strokePath()
        }
        return image.withRenderingMode(.alwaysTemplate)
    }
}
