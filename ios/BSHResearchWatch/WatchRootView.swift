import SwiftUI

enum WatchHubRoute: Hashable {
    case home
    case tape
    case movers
    case news
    case pulse
    case settings
}

struct WatchRootView: View {
    @EnvironmentObject private var quotes: WatchQuotesStore
    @State private var route: WatchHubRoute = .home

    var body: some View {
        Group {
            switch route {
            case .home:
                homeForLayout
            case .tape:
                WatchDetailShell(title: "Tape", route: $route) { TapeDetail() }
            case .movers:
                WatchDetailShell(title: "Movers", route: $route) { MoversDetail() }
            case .news:
                WatchDetailShell(title: "News", route: $route) { NewsDetail() }
            case .pulse:
                WatchDetailShell(title: "Pulse", route: $route) { PulseDetail() }
            case .settings:
                WatchDetailShell(title: "Settings", route: $route) { SettingsDetail() }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .foregroundStyle(WatchTheme.text)
        .background(WatchTheme.canvas.ignoresSafeArea())
        .environment(\.colorScheme, .light)
        .preferredColorScheme(.light)
        .task {
            await quotes.refresh()
        }
    }

    @ViewBuilder
    private var homeForLayout: some View {
        switch quotes.layoutStyle {
        case .deskHome:
            WatchDeskHome(route: $route)
        case .tileHub:
            WatchHubHome(route: $route)
        case .heroTicker:
            WatchHeroTickerHome(route: $route)
        }
    }
}

// MARK: - Live tape (2 names)

/// Fixed strip — no GeometryReader marquee (that rendered empty in ScrollView).
struct LiveTapeStrip: View {
    let quotes: [WatchQuote]

    var body: some View {
        let items = Array((quotes.isEmpty ? WatchConfig.demoQuotes() : quotes).prefix(2))
        HStack(spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.element.id) { index, quote in
                HStack(spacing: 4) {
                    Text(quote.ticker)
                        .font(.system(size: 12, weight: .bold).monospaced())
                        .foregroundStyle(WatchTheme.text)
                        .fixedSize(horizontal: true, vertical: false)
                    Text(quote.pctText)
                        .font(.system(size: 12, weight: .semibold).monospacedDigit())
                        .foregroundStyle(quote.isUp ? Color.green : Color.red)
                        .fixedSize(horizontal: true, vertical: false)
                }
                .frame(maxWidth: .infinity, alignment: index == 0 ? .leading : .trailing)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(WatchTheme.cardFill, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .accessibilityLabel(items.map(\.tapeText).joined(separator: ", "))
    }
}

// MARK: - A · Desk Home

struct WatchDeskHome: View {
    @EnvironmentObject private var quotes: WatchQuotesStore
    @Binding var route: WatchHubRoute
    @Environment(\.openURL) private var openURL

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                LiveTapeStrip(quotes: quotes.featureQuotes)
                    .onTapGesture { route = .tape }

                VStack(spacing: 0) {
                    ForEach(Array(quotes.tapeQuotes.prefix(5).enumerated()), id: \.element.id) { index, quote in
                        Button {
                            if let url = WatchConfig.phoneDeepLink(ticker: quote.ticker) {
                                openURL(url)
                            }
                        } label: {
                            WatchQuoteRow(quote: quote, showName: true)
                        }
                        .buttonStyle(.plain)
                        if index < min(4, quotes.tapeQuotes.count - 1) {
                            Divider().opacity(0.35)
                        }
                    }
                }

                Button { route = .news } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 4) {
                            Image(systemName: "doc.text")
                                .font(.system(size: 9, weight: .semibold))
                            Text("MARKET NEWS")
                                .font(.system(size: 9, weight: .bold))
                                .tracking(0.4)
                        }
                        .foregroundStyle(WatchTheme.muted)

                        Text(quotes.news.first?.title ?? (quotes.loading ? "Loading headlines…" : "No headlines yet"))
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(WatchTheme.text)
                            .multilineTextAlignment(.leading)
                            .lineLimit(3)

                        if let item = quotes.news.first {
                            HStack(spacing: 4) {
                                if let source = item.source, !source.isEmpty {
                                    Text(source)
                                }
                                if !item.timeText.isEmpty {
                                    Text("•")
                                    Text("\(item.timeText) ago")
                                }
                            }
                            .font(.system(size: 10))
                            .foregroundStyle(WatchTheme.muted)
                        }
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(WatchTheme.cardFill, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain)

                Button { route = .pulse } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "waveform.path.ecg")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(WatchTheme.text)
                        Text("Pulse:")
                            .font(.system(size: 11, weight: .bold))
                        Text(quotes.pulseHeadline)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(WatchTheme.muted)
                            .lineLimit(2)
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 4)
                }
                .buttonStyle(.plain)

                homeChrome
            }
            .padding(.horizontal, 4)
            .padding(.bottom, 6)
        }
    }

    private var homeChrome: some View {
        HStack {
            Text("BSH")
                .font(.caption2.weight(.bold))
                .foregroundStyle(WatchTheme.muted)
            if quotes.stale {
                Text("cached")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.orange)
            }
            Spacer()
            Button {
                Task { await quotes.refresh() }
            } label: {
                if quotes.loading {
                    ProgressView().scaleEffect(0.6)
                } else {
                    Image(systemName: "arrow.clockwise")
                        .font(.caption2.weight(.semibold))
                }
            }
            .buttonStyle(.plain)
            Button { route = .settings } label: {
                Image(systemName: "gearshape")
                    .font(.caption2.weight(.semibold))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 2)
    }
}

// MARK: - B · Tile Hub

struct WatchHubHome: View {
    @EnvironmentObject private var quotes: WatchQuotesStore
    @Binding var route: WatchHubRoute

    private let columns = [
        GridItem(.flexible(), spacing: 6),
        GridItem(.flexible(), spacing: 6),
    ]

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                LiveTapeStrip(quotes: quotes.featureQuotes)
                    .onTapGesture { route = .tape }

                LazyVGrid(columns: columns, spacing: 6) {
                    HubTile(
                        title: "Tape",
                        systemImage: "chart.line.uptrend.xyaxis"
                    ) {
                        LiveTapeDuo(
                            quotes: quotes.featureQuotes,
                            sparks: quotes.sparks
                        )
                    } action: { route = .tape }

                    HubTile(
                        title: "Movers",
                        systemImage: "arrow.up.arrow.down"
                    ) {
                        HStack(spacing: 8) {
                            VStack(spacing: 1) {
                                Text("\(max(quotes.gainers.count, quotes.tapeQuotes.filter(\.isUp).count))")
                                    .font(.title3.weight(.bold))
                                    .foregroundStyle(.green)
                                Text("Up")
                                    .font(.system(size: 9))
                                    .foregroundStyle(WatchTheme.muted)
                            }
                            Rectangle()
                                .fill(WatchTheme.hairline)
                                .frame(width: 1, height: 28)
                            VStack(spacing: 1) {
                                Text("\(max(quotes.losers.count, quotes.tapeQuotes.filter { !$0.isUp }.count))")
                                    .font(.title3.weight(.bold))
                                    .foregroundStyle(.red)
                                Text("Down")
                                    .font(.system(size: 9))
                                    .foregroundStyle(WatchTheme.muted)
                            }
                        }
                    } action: { route = .movers }

                    HubTile(
                        title: "News",
                        systemImage: "newspaper",
                        accent: .orange
                    ) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(quotes.news.first?.title ?? (quotes.loading ? "Loading…" : "No headlines"))
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(WatchTheme.text)
                                .lineLimit(3)
                                .multilineTextAlignment(.leading)
                            if let age = quotes.news.first?.timeText, !age.isEmpty {
                                Text(age)
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 2)
                                    .background(Color.orange, in: Capsule())
                            }
                        }
                    } action: { route = .news }

                    HubTile(
                        title: "Pulse",
                        systemImage: "waveform.path.ecg"
                    ) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(quotes.pulse == nil ? "Brief" : "Live")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(WatchTheme.muted)
                            Text(quotes.pulseHeadline)
                                .font(.system(size: 10, weight: .medium))
                                .lineLimit(3)
                                .multilineTextAlignment(.leading)
                        }
                    } action: { route = .pulse }
                }

                HStack {
                    Text("BSH")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(WatchTheme.muted)
                    Spacer()
                    Button {
                        Task { await quotes.refresh() }
                    } label: {
                        if quotes.loading {
                            ProgressView().scaleEffect(0.6)
                        } else {
                            Image(systemName: "arrow.clockwise")
                                .font(.caption2.weight(.semibold))
                        }
                    }
                    .buttonStyle(.plain)
                    Button {
                        route = .settings
                    } label: {
                        Image(systemName: "gearshape")
                            .font(.caption2.weight(.semibold))
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 2)
            }
            .padding(.horizontal, 4)
            .padding(.bottom, 6)
        }
    }
}

/// Two compact live names for the Tape tile.
/// Sparklines only when we have a real last-day series — no fake waves.
private struct LiveTapeDuo: View {
    let quotes: [WatchQuote]
    let sparks: [String: WatchSparkSeries]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(quotes.prefix(2)) { quote in
                let spark = sparks[quote.ticker]
                let hasLiveSpark = (spark?.closes.count ?? 0) > 1

                VStack(alignment: .leading, spacing: 2) {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text(quote.ticker)
                            .font(.system(size: 12, weight: .bold).monospaced())
                            .foregroundStyle(WatchTheme.text)
                            .fixedSize(horizontal: true, vertical: false)
                        Spacer(minLength: 2)
                        Text(quote.pctText)
                            .font(.system(size: 11, weight: .bold).monospacedDigit())
                            .foregroundStyle(quote.isUp ? Color.green : Color.red)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    if let name = quote.shortName {
                        Text(name)
                            .font(.system(size: 9, weight: .medium))
                            .foregroundStyle(WatchTheme.muted)
                            .lineLimit(1)
                    }
                    if hasLiveSpark, let spark {
                        LiveMiniSpark(closes: spark.closes, isUp: spark.isUp || quote.isUp)
                            .frame(height: 14)
                    }
                }
            }
        }
    }
}

private struct LiveMiniSpark: View {
    let closes: [Double]
    let isUp: Bool

    var body: some View {
        Canvas { context, size in
            guard closes.count > 1,
                  let minV = closes.min(),
                  let maxV = closes.max()
            else { return }
            let span = max(maxV - minV, 0.0001)
            var path = Path()
            for (i, v) in closes.enumerated() {
                let x = size.width * CGFloat(i) / CGFloat(closes.count - 1)
                let y = size.height * (1 - CGFloat((v - minV) / span))
                if i == 0 { path.move(to: CGPoint(x: x, y: y)) }
                else { path.addLine(to: CGPoint(x: x, y: y)) }
            }
            context.stroke(
                path,
                with: .color(isUp ? Color.green.opacity(0.9) : Color.red.opacity(0.9)),
                style: StrokeStyle(lineWidth: 1.4, lineJoin: .round)
            )
        }
    }
}

private struct HubTile<Content: View>: View {
    let title: String
    let systemImage: String
    var accent: Color = WatchTheme.text
    @ViewBuilder var content: Content
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 3) {
                    Image(systemName: systemImage)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(accent)
                    Text(title)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(WatchTheme.text)
                    Spacer(minLength: 0)
                }
                content
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
            .padding(7)
            .frame(maxWidth: .infinity, minHeight: 78, alignment: .topLeading)
            .background(WatchTheme.cardFill, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

private enum WatchTheme {
    static let canvas = Color.white
    static let cardFill = Color(white: 0.92)
    static let cardFillSelected = Color(white: 0.84)
    /// Explicit ink — watchOS often keeps white `.primary` even with a light shell.
    static let text = Color.black
    static let muted = Color(white: 0.35)
    static let hairline = Color(white: 0.75)
}

// MARK: - C · Hero Ticker

struct WatchHeroTickerHome: View {
    @EnvironmentObject private var quotes: WatchQuotesStore
    @Binding var route: WatchHubRoute
    @State private var page = 0
    @Environment(\.openURL) private var openURL

    private var heroes: [WatchQuote] {
        Array(quotes.tapeQuotes.prefix(5))
    }

    var body: some View {
        VStack(spacing: 4) {
            // Horizontal page TabView only — never nest NavigationStack/List in a vertical TabView.
            TabView(selection: $page) {
                ForEach(Array(heroes.enumerated()), id: \.element.id) { index, quote in
                    Button {
                        if let url = WatchConfig.phoneDeepLink(ticker: quote.ticker) {
                            openURL(url)
                        }
                    } label: {
                        VStack(spacing: 1) {
                            Text(quote.ticker)
                                .font(.system(size: 30, weight: .bold).monospaced())
                                .foregroundStyle(WatchTheme.text)
                            Text(quote.priceText)
                                .font(.system(size: 24, weight: .bold).monospacedDigit())
                                .foregroundStyle(WatchTheme.text)
                            Text(quote.pctText)
                                .font(.system(size: 16, weight: .bold).monospacedDigit())
                                .foregroundStyle(quote.isUp ? Color.green : Color.red)
                            Spacer(minLength: 0)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                        .padding(.top, 2)
                    }
                    .buttonStyle(.plain)
                    .tag(index)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .automatic))
            .frame(maxHeight: .infinity)
            .layoutPriority(1)

            HStack(spacing: 6) {
                heroChip("News", systemImage: "newspaper") { route = .news }
                heroChip("Pulse", systemImage: "waveform.path.ecg") { route = .pulse }
                heroChip("List", systemImage: "list.bullet") { route = .tape }
            }

            HStack {
                Button { route = .settings } label: {
                    Image(systemName: "gearshape")
                        .font(.caption2.weight(.semibold))
                }
                .buttonStyle(.plain)
                Spacer()
                Button {
                    Task { await quotes.refresh() }
                } label: {
                    if quotes.loading {
                        ProgressView().scaleEffect(0.55)
                    } else {
                        Image(systemName: "arrow.clockwise")
                            .font(.caption2.weight(.semibold))
                    }
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 4)
            .padding(.bottom, 2)
        }
        .padding(.horizontal, 4)
        .onChange(of: heroes.count) { _, count in
            if page >= count { page = max(0, count - 1) }
        }
    }

    private func heroChip(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 3) {
                Image(systemName: systemImage)
                    .font(.system(size: 9, weight: .semibold))
                Text(title)
                    .font(.system(size: 10, weight: .semibold))
            }
            .foregroundStyle(WatchTheme.text)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .overlay(
                Capsule()
                    .stroke(WatchTheme.hairline, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Detail shell

private struct WatchDetailShell<Content: View>: View {
    let title: String
    @Binding var route: WatchHubRoute
    @ViewBuilder var content: Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Button {
                        route = .home
                    } label: {
                        Label("Back", systemImage: "chevron.left")
                            .font(.caption2.weight(.semibold))
                    }
                    .buttonStyle(.plain)
                    Spacer()
                    Text(title)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(WatchTheme.muted)
                }
                content
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 6)
            .padding(.bottom, 8)
        }
    }
}

private struct WatchCard<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(.vertical, 4)
            .padding(.horizontal, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(WatchTheme.cardFill, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

// MARK: - Details

struct TapeDetail: View {
    @EnvironmentObject private var quotes: WatchQuotesStore
    @Environment(\.openURL) private var openURL

    var body: some View {
        LiveTapeDuo(
            quotes: quotes.featureQuotes,
            sparks: quotes.sparks
        )
        .padding(.vertical, 6)
        .padding(.horizontal, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(WatchTheme.cardFill, in: RoundedRectangle(cornerRadius: 10, style: .continuous))

        LiveTapeStrip(quotes: quotes.featureQuotes)
            .padding(.bottom, 4)

        ForEach(quotes.tapeQuotes) { quote in
            Button {
                if let url = WatchConfig.phoneDeepLink(ticker: quote.ticker) { openURL(url) }
            } label: {
                WatchQuoteRow(quote: quote)
            }
            .buttonStyle(.plain)
        }
        refreshButton
    }

    private var refreshButton: some View {
        Button {
            Task { await quotes.refresh() }
        } label: {
            HStack(spacing: 4) {
                if quotes.loading { ProgressView().scaleEffect(0.7) }
                Text("Refresh").font(.caption.weight(.semibold))
            }
        }
        .buttonStyle(.bordered)
    }
}

struct MoversDetail: View {
    @EnvironmentObject private var quotes: WatchQuotesStore
    @Environment(\.openURL) private var openURL

    var body: some View {
        section("Gainers")
        let gainers = quotes.gainers.isEmpty ? quotes.tapeQuotes.filter(\.isUp) : quotes.gainers
        if gainers.isEmpty {
            Text(quotes.loading ? "Loading…" : "—").font(.caption2).foregroundStyle(WatchTheme.muted)
        }
        ForEach(gainers) { quote in moverRow(quote) }

        section("Losers")
        let losers = quotes.losers.isEmpty ? quotes.tapeQuotes.filter { !$0.isUp } : quotes.losers
        if losers.isEmpty {
            Text("—").font(.caption2).foregroundStyle(WatchTheme.muted)
        }
        ForEach(losers) { quote in moverRow(quote) }

        if !quotes.active.isEmpty {
            section("Active")
            ForEach(quotes.active.prefix(4)) { quote in moverRow(quote) }
        }
    }

    private func section(_ text: String) -> some View {
        Text(text)
            .font(.caption2.weight(.bold))
            .foregroundStyle(WatchTheme.muted)
            .padding(.top, 2)
    }

    private func moverRow(_ quote: WatchQuote) -> some View {
        Button {
            if let url = WatchConfig.phoneDeepLink(ticker: quote.ticker) { openURL(url) }
        } label: {
            WatchQuoteRow(quote: quote, showName: true)
        }
        .buttonStyle(.plain)
    }
}

struct NewsDetail: View {
    @EnvironmentObject private var quotes: WatchQuotesStore
    @Environment(\.openURL) private var openURL

    var body: some View {
        if quotes.news.isEmpty {
            Text(quotes.loading ? "Loading headlines…" : "No headlines")
                .font(.caption)
                .foregroundStyle(WatchTheme.muted)
        }
        ForEach(quotes.news) { item in
            Button {
                if let ticker = item.ticker,
                   let url = WatchConfig.phoneDeepLink(ticker: ticker) {
                    openURL(url)
                } else if let raw = item.url, let url = URL(string: raw) {
                    openURL(url)
                }
            } label: {
                WatchCard {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(item.title)
                            .font(.caption.weight(.semibold))
                            .lineLimit(3)
                            .multilineTextAlignment(.leading)
                        HStack(spacing: 4) {
                            if let ticker = item.ticker {
                                Text(ticker)
                                    .font(.caption2.monospaced().weight(.bold))
                                    .foregroundStyle(.orange)
                            }
                            if let source = item.source, !source.isEmpty {
                                Text(source)
                                    .font(.caption2)
                                    .foregroundStyle(WatchTheme.muted)
                                    .lineLimit(1)
                            }
                            Spacer(minLength: 2)
                            if !item.timeText.isEmpty {
                                Text(item.timeText)
                                    .font(.caption2.monospacedDigit())
                                    .foregroundStyle(WatchTheme.muted)
                            }
                        }
                    }
                }
            }
            .buttonStyle(.plain)
        }
    }
}

struct PulseDetail: View {
    @EnvironmentObject private var quotes: WatchQuotesStore
    @Environment(\.openURL) private var openURL

    var body: some View {
        if quotes.pulse == nil {
            Text(quotes.loading ? "Loading brief…" : "No morning brief on server yet")
                .font(.caption)
                .foregroundStyle(WatchTheme.muted)
        } else {
            WatchCard {
                VStack(alignment: .leading, spacing: 4) {
                    Text(quotes.pulseHeadline)
                        .font(.caption.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    if let date = quotes.pulse?.date {
                        Text(date).font(.caption2).foregroundStyle(WatchTheme.muted)
                    }
                    ForEach(Array(quotes.pulseBullets.enumerated()), id: \.offset) { _, bullet in
                        Text("• \(bullet)")
                            .font(.caption2)
                            .foregroundStyle(WatchTheme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            if !quotes.pulseIndices.isEmpty {
                Text("Indices").font(.caption2.weight(.bold)).foregroundStyle(WatchTheme.muted)
                ForEach(quotes.pulseIndices) { quote in
                    Button { openTicker(quote.ticker) } label: { WatchQuoteRow(quote: quote) }
                        .buttonStyle(.plain)
                }
            }

            if !quotes.pulseGainers.isEmpty {
                Text("Brief ↑").font(.caption2.weight(.bold)).foregroundStyle(WatchTheme.muted)
                ForEach(quotes.pulseGainers) { quote in
                    Button { openTicker(quote.ticker) } label: { WatchQuoteRow(quote: quote) }
                        .buttonStyle(.plain)
                }
            }

            if !quotes.pulseLosers.isEmpty {
                Text("Brief ↓").font(.caption2.weight(.bold)).foregroundStyle(WatchTheme.muted)
                ForEach(quotes.pulseLosers) { quote in
                    Button { openTicker(quote.ticker) } label: { WatchQuoteRow(quote: quote) }
                        .buttonStyle(.plain)
                }
            }

            if !quotes.pulseAlerts.isEmpty {
                Text("Alerts").font(.caption2.weight(.bold)).foregroundStyle(WatchTheme.muted)
                ForEach(quotes.pulseAlerts) { alert in
                    WatchCard {
                        VStack(alignment: .leading, spacing: 2) {
                            if let ticker = alert.ticker {
                                Text(ticker).font(.caption.monospaced().weight(.bold))
                            }
                            Text(alert.message ?? alert.kind ?? "Alert")
                                .font(.caption2)
                                .foregroundStyle(WatchTheme.muted)
                                .lineLimit(3)
                        }
                    }
                }
            }
        }
    }

    private func openTicker(_ ticker: String) {
        if let url = WatchConfig.phoneDeepLink(ticker: ticker) { openURL(url) }
    }
}

struct SettingsDetail: View {
    @State private var baseURL = WatchConfig.baseURL.absoluteString
    @State private var saved = false
    @EnvironmentObject private var quotes: WatchQuotesStore

    var body: some View {
        Text("Home layout")
            .font(.caption2.weight(.bold))
            .foregroundStyle(WatchTheme.muted)

        VStack(spacing: 6) {
            ForEach(WatchLayoutStyle.allCases) { style in
                Button {
                    quotes.setLayoutStyle(style)
                } label: {
                    HStack {
                        Text(style.title)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(WatchTheme.text)
                        Spacer()
                        if quotes.layoutStyle == style {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.green)
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 7)
                    .background(
                        quotes.layoutStyle == style ? WatchTheme.cardFillSelected : WatchTheme.cardFill,
                        in: RoundedRectangle(cornerRadius: 8, style: .continuous)
                    )
                }
                .buttonStyle(.plain)
            }
        }

        Text("API base URL")
            .font(.caption2.weight(.bold))
            .foregroundStyle(WatchTheme.muted)
            .padding(.top, 6)
        TextField("http://…", text: $baseURL)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .font(.caption.monospaced())
        Button("Save & refresh") {
            WatchConfig.saveBaseURL(baseURL)
            saved = true
            Task { await quotes.refresh() }
        }
        .buttonStyle(.borderedProminent)
        if saved {
            Text("Saved").font(.caption2).foregroundStyle(.green)
        }

        Text("Pins (tape)")
            .font(.caption2.weight(.bold))
            .foregroundStyle(WatchTheme.muted)
            .padding(.top, 4)
        Text("Live duo")
            .font(.system(size: 9, weight: .bold))
            .foregroundStyle(WatchTheme.muted)
        ForEach(WatchConfig.featureCompanyTickers(), id: \.self) { ticker in
            Text(ticker).font(.body.monospaced())
        }
        Text("Full tape")
            .font(.system(size: 9, weight: .bold))
            .foregroundStyle(WatchTheme.muted)
            .padding(.top, 2)
        ForEach(WatchConfig.resolvedTapeTickers(), id: \.self) { ticker in
            Text(ticker).font(.caption.monospaced())
        }
        Text("Edit pins on iPhone Settings. Tape tile shows the first two equities (default NVDA / AAPL).")
            .font(.system(size: 9))
            .foregroundStyle(WatchTheme.muted)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - Shared row

struct WatchQuoteRow: View {
    let quote: WatchQuote
    var showName = false

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            VStack(alignment: .leading, spacing: 1) {
                Text(quote.ticker)
                    .font(.headline.monospaced())
                if showName, let name = quote.name, !name.isEmpty {
                    Text(name)
                        .font(.caption2)
                        .foregroundStyle(WatchTheme.muted)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 4)
            VStack(alignment: .trailing, spacing: 1) {
                Text(quote.priceText)
                    .font(.body.monospacedDigit().weight(.semibold))
                Text(quote.pctText)
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .foregroundStyle(quote.isUp ? Color.green : Color.red)
            }
        }
        .padding(.vertical, 2)
    }
}
