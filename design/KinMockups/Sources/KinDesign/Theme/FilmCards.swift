import SwiftUI

/// Title cards and overlays for the launch film (docs/pitch/LAUNCH_VIDEO.md), 1920 x 1080. Plain SF Pro on black,
/// centered, as the shot list asks; the reveal and close use the wordmark. Overlays are transparent PNGs.
public enum FilmCards {
    static let w: CGFloat = 1920, h: CGFloat = 1080

    static func black<C: View>(@ViewBuilder _ c: () -> C) -> some View {
        ZStack { Color.black; c() }.frame(width: w, height: h)
    }
    static func line(_ t: String, size: CGFloat = 72, weight: Font.Weight = .semibold, opacity: Double = 1) -> some View {
        Text(t).font(.system(size: size, weight: weight)).foregroundStyle(Color.white.opacity(opacity)).multilineTextAlignment(.center)
    }

    @MainActor public static var all: [(String, AnyView)] {
        [
            ("02a-whos-lin", AnyView(black { line("Who's Lin?") })),
            ("02b-six-weeks-ago", AnyView(black { line("She told him. Six weeks ago.") })),
            ("03-reveal", AnyView(black {
                VStack(spacing: 40) {
                    Wordmark(height: 150)
                    line("Common ground for people who live apart.", size: 44, weight: .regular, opacity: 0.82)
                }
            })),
            ("06-six-weeks-later", AnyView(black {
                VStack(spacing: 22) {
                    line("Six weeks later", size: 80)
                    line("Time advanced with a dev clock for this demo.", size: 30, weight: .regular, opacity: 0.6)
                }
            })),
            ("11-proof", AnyView(black { Proof() })),
            ("13-close", AnyView(black {
                VStack(spacing: 36) {
                    Wordmark(height: 130)
                    line("Common ground for people who live apart.", size: 42, weight: .regular, opacity: 0.82)
                    VStack(spacing: 10) {
                        line("Built at HackTX 2026 on Meta Muse Spark and Muse Voice Transcribe,", size: 24, weight: .regular, opacity: 0.55)
                        line("with LiveKit, ElevenLabs, Twilio and SwiftUI. Code written with Claude Code.", size: 24, weight: .regular, opacity: 0.55)
                        line("github.com/LordKarV/hacktx", size: 24, weight: .medium, opacity: 0.75)
                    }
                    .padding(.top, 30)
                }
            })),
            ("overlay-september", AnyView(LowerThird(text: "September"))),
            ("overlay-next-day", AnyView(LowerThird(text: "Next day"))),
            ("overlay-no-card", AnyView(ZStack(alignment: .topTrailing) {
                Color.clear
                Text("No card.").font(.system(size: 54, weight: .semibold)).foregroundStyle(.white)
                    .padding(.horizontal, 34).padding(.vertical, 18).background(Color.black.opacity(0.6), in: Capsule())
                    .padding(80)
            }.frame(width: w, height: h))),
        ]
    }

    /// Shot 11: two bars and the collision line. Numbers are the committed live eval (backend/eval/results.md).
    struct Proof: View {
        var body: some View {
            VStack(alignment: .leading, spacing: 44) {
                Text("Names and relationships wrong").font(.system(size: 40, weight: .semibold)).foregroundStyle(Color.white.opacity(0.7))
                bar("Generic translation", value: 0.54, label: "54%", color: Color(hex: 0x8A8D91))
                bar("KIN", value: 0.01, label: "1%", color: BrandColor.warm)
                Text("Two people with the same name: 97% wrong vs 0%.").font(.system(size: 36, weight: .medium)).foregroundStyle(.white)
                    .padding(.top, 10)
                Text("Muse Spark 1.3, same model and context with and without KIN's graph. 105-sentence Tamil family test set, 150 entity spans.")
                    .font(.system(size: 22)).foregroundStyle(Color.white.opacity(0.5))
            }
            .frame(width: 1400, alignment: .leading)
        }
        func bar(_ name: String, value: CGFloat, label: String, color: Color) -> some View {
            HStack(spacing: 28) {
                Text(name).font(.system(size: 34, weight: .medium)).foregroundStyle(.white).frame(width: 380, alignment: .leading)
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.white.opacity(0.08)).frame(width: 760, height: 44)
                    Capsule().fill(color).frame(width: max(44, 760 * value / 0.6), height: 44)
                }
                Text(label).font(.system(size: 44, weight: .bold, design: .rounded)).foregroundStyle(.white)
            }
        }
    }

    struct LowerThird: View {
        let text: String
        var body: some View {
            ZStack(alignment: .bottomLeading) {
                Color.clear
                Text(text).font(.system(size: 46, weight: .semibold)).foregroundStyle(.white)
                    .padding(.horizontal, 30).padding(.vertical, 14)
                    .background(Color.black.opacity(0.55), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .padding(.leading, 96).padding(.bottom, 110)
            }
            .frame(width: FilmCards.w, height: FilmCards.h)
        }
    }
}
