import SwiftUI

/// Large page title tucked under the status bar (no system large-title gap).
struct CompactPageHeader<Trailing: View>: View {
    let title: String
    var searchText: Binding<String>? = nil
    var searchPrompt: String = ""
    @ViewBuilder var trailing: () -> Trailing

    init(
        title: String,
        searchText: Binding<String>? = nil,
        searchPrompt: String = "",
        @ViewBuilder trailing: @escaping () -> Trailing = { EmptyView() }
    ) {
        self.title = title
        self.searchText = searchText
        self.searchPrompt = searchPrompt
        self.trailing = trailing
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(title)
                    .font(.largeTitle.weight(.bold))
                    .frame(maxWidth: .infinity, alignment: .leading)
                trailing()
            }

            if let searchText {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)
                    TextField(searchPrompt, text: searchText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    if !searchText.wrappedValue.isEmpty {
                        Button {
                            searchText.wrappedValue = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.tertiary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 4)
        .padding(.bottom, 8)
        .background(Color(.systemGroupedBackground))
    }
}

extension View {
    /// Compact large title under the status bar; hides the system nav bar on this root screen.
    func compactRootChrome<Trailing: View>(
        title: String,
        searchText: Binding<String>? = nil,
        searchPrompt: String = "",
        @ViewBuilder trailing: @escaping () -> Trailing = { EmptyView() }
    ) -> some View {
        self
            .contentMargins(.top, 0, for: .scrollContent)
            .safeAreaInset(edge: .top, spacing: 0) {
                CompactPageHeader(
                    title: title,
                    searchText: searchText,
                    searchPrompt: searchPrompt,
                    trailing: trailing
                )
            }
            .toolbar(.hidden, for: .navigationBar)
    }
}
