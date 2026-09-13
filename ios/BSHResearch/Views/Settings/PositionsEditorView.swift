import SwiftUI

struct PositionsEditorView: View {
    @EnvironmentObject private var desk: DeskStore
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var session: SessionStore
    @State private var ticker = ""
    @State private var shares = ""
    @State private var cost = ""

    var body: some View {
        Form {
            if !session.canWriteDesk {
                Section {
                    Text(language.t("roles.read_only_hint"))
                        .foregroundStyle(.secondary)
                }
            }

            Section(language.t("positions.add")) {
                TextField("Ticker", text: $ticker)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .disabled(!session.canWriteDesk)
                TextField(language.t("positions.shares"), text: $shares)
                    .keyboardType(.decimalPad)
                    .disabled(!session.canWriteDesk)
                TextField(language.t("positions.cost"), text: $cost)
                    .keyboardType(.decimalPad)
                    .disabled(!session.canWriteDesk)
                Button(language.t("common.add")) {
                    Task { await addLot() }
                }
                .disabled(!session.canWriteDesk || ticker.isEmpty || Double(shares) == nil)
            }

            Section(language.t("positions.title")) {
                if desk.bookLots.isEmpty {
                    Text(language.t("positions.empty")).foregroundStyle(.secondary)
                } else {
                    ForEach(desk.bookLots) { lot in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(lot.ticker).font(.headline)
                                Text("\(format(lot.shares)) sh @ \(format(lot.costBasis))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                        }
                        .swipeActions {
                            if session.canWriteDesk {
                                Button(role: .destructive) {
                                    Task { await desk.removeLot(id: lot.id) }
                                } label: {
                                    Label(language.t("common.remove"), systemImage: "trash")
                                }
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle(language.t("positions.title"))
        .task { await desk.loadIfNeeded() }
    }

    private func addLot() async {
        guard session.canWriteDesk else { return }
        let t = ticker.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard let sh = Double(shares) else { return }
        let basis = Double(cost) ?? 0
        await desk.upsertLot(BookLot(id: UUID().uuidString, ticker: t, shares: sh, costBasis: basis))
        ticker = ""
        shares = ""
        cost = ""
    }

    private func format(_ value: Double) -> String {
        String(format: value.rounded() == value ? "%.0f" : "%.2f", value)
    }
}
