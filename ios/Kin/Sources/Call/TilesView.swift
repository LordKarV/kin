import LiveKit
import SwiftUI

/// Peer video tiles plus a self preview. Built for 1:1 (the remote fills the screen, self is a small corner view);
/// 2 to 8 peers fall back to a two-column grid sized to fit the space. More than 8 shows the first 8 and "+N more".
struct TilesView: View {
    static let maxPeers = 8
    let peers: [Tile]
    let me: Tile?

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            main
            if let me, !peers.isEmpty {
                TileView(tile: me, mirror: true)
                    .frame(width: 110, height: 160)
                    .padding(12)
            }
        }
        .background(Theme.background)
    }

    @ViewBuilder private var main: some View {
        let shown = Array(peers.prefix(Self.maxPeers))
        switch shown.count {
        case 0:
            if let me { TileView(tile: me, mirror: true, caption: "Waiting for the other person") } else { Color.clear }
        case 1:
            TileView(tile: shown[0])
        default:
            GeometryReader { geo in
                let spacing: CGFloat = 8
                let rows = CGFloat((shown.count + 1) / 2)
                let height = max(0, (geo.size.height - spacing * (rows + 1)) / rows)
                VStack(spacing: spacing) {
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: spacing), GridItem(.flexible(), spacing: spacing)],
                              spacing: spacing) {
                        ForEach(shown) { TileView(tile: $0).frame(height: height) }
                    }
                    Spacer(minLength: 0)
                }
                .padding(spacing)
            }
            .overlay(alignment: .topLeading) {
                if peers.count > Self.maxPeers {
                    Text("+\(peers.count - Self.maxPeers) more")
                        .font(.caption.bold())
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(.black.opacity(0.5), in: Capsule())
                        .padding(16)
                }
            }
        }
    }
}

/// One tile: video when there is a track, else the initial on the surface color; name label at the bottom.
struct TileView: View {
    let tile: Tile
    var mirror = false
    var caption: String?

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            Theme.surface
            if let track = tile.track {
                SwiftUIVideoView(track, layoutMode: .fill, mirrorMode: mirror ? .auto : .off)
            } else {
                Text(String(tile.name.prefix(1)).uppercased())
                    .font(.largeTitle.bold())
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            VStack(alignment: .leading, spacing: 2) {
                if let caption { Text(caption).font(.footnote) }
                Text(tile.name).font(.caption.bold())
            }
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(.black.opacity(0.5), in: Capsule())
            .padding(8)
        }
        .clipShape(RoundedRectangle(cornerRadius: Theme.radius))
        .accessibilityElement(children: .combine)
        .accessibilityLabel(tile.name)
    }
}
