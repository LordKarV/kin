import SwiftUI
import AppKit
import KinDesign

/// Writes `design/brand/`: an asset catalog ready to copy into ios/Kin/Resources/, launch screen previews, and the
/// launch film cards. App icon PNGs are written without an alpha channel where the App Store requires it.
@MainActor func renderBrand(_ out: String) {
    let fm = FileManager.default
    func dir(_ p: String) -> String { let d = "\(out)/\(p)"; try? fm.createDirectory(atPath: d, withIntermediateDirectories: true); return d }
    func write(_ text: String, _ path: String) { try! text.write(toFile: path, atomically: true, encoding: .utf8) }

    func cg<V: View>(_ v: V, scale: CGFloat) -> CGImage {
        let r = ImageRenderer(content: v); r.scale = scale
        return r.cgImage!
    }
    func save(_ image: CGImage, _ path: String, opaque: Bool = false) {
        var img = image
        if opaque {  // flatten onto an RGB context with no alpha (App Store rejects icons with an alpha channel)
            let ctx = CGContext(data: nil, width: image.width, height: image.height, bitsPerComponent: 8, bytesPerRow: 0,
                                space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
            ctx.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            img = ctx.makeImage()!
        }
        try! NSBitmapImageRep(cgImage: img).representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: path))
        print("wrote \(path.replacingOccurrences(of: out + "/", with: "")) \(img.width)x\(img.height)")
    }

    let cat = dir("Assets.xcassets")
    write(#"{"info":{"author":"xcode","version":1}}"#, "\(cat)/Contents.json")

    // App icon (single 1024 size, iOS 18 light / dark / tinted appearances)
    let icon = dir("Assets.xcassets/AppIcon.appiconset")
    save(cg(AppIconArt(.light), scale: 1), "\(icon)/AppIcon.png", opaque: true)
    save(cg(AppIconArt(.dark), scale: 1), "\(icon)/AppIcon-dark.png")
    save(cg(AppIconArt(.tinted), scale: 1), "\(icon)/AppIcon-tinted.png")
    write(#"""
    {"images":[
     {"filename":"AppIcon.png","idiom":"universal","platform":"ios","size":"1024x1024"},
     {"appearances":[{"appearance":"luminosity","value":"dark"}],"filename":"AppIcon-dark.png","idiom":"universal","platform":"ios","size":"1024x1024"},
     {"appearances":[{"appearance":"luminosity","value":"tinted"}],"filename":"AppIcon-tinted.png","idiom":"universal","platform":"ios","size":"1024x1024"}],
     "info":{"author":"xcode","version":1}}
    """#, "\(icon)/Contents.json")

    // Launch screen: background color + centered mark (UILaunchScreen: UIColorName / UIImageName)
    let bg = dir("Assets.xcassets/LaunchBackground.colorset")
    write(#"""
    {"colors":[
     {"color":{"color-space":"srgb","components":{"alpha":"1.000","blue":"0xF5","green":"0xF2","red":"0xF0"}},"idiom":"universal"},
     {"appearances":[{"appearance":"luminosity","value":"dark"}],"color":{"color-space":"srgb","components":{"alpha":"1.000","blue":"0x1A","green":"0x19","red":"0x18"}},"idiom":"universal"}],
     "info":{"author":"xcode","version":1}}
    """#, "\(bg)/Contents.json")
    let mark = dir("Assets.xcassets/LaunchMark.imageset")
    save(cg(LaunchMarkArt(), scale: 2), "\(mark)/LaunchMark@2x.png")
    save(cg(LaunchMarkArt(), scale: 3), "\(mark)/LaunchMark@3x.png")
    write(#"""
    {"images":[{"idiom":"universal","scale":"1x"},{"filename":"LaunchMark@2x.png","idiom":"universal","scale":"2x"},{"filename":"LaunchMark@3x.png","idiom":"universal","scale":"3x"}],
     "info":{"author":"xcode","version":1}}
    """#, "\(mark)/Contents.json")
    let accent = dir("Assets.xcassets/AccentColor.colorset")
    write(#"""
    {"colors":[
     {"color":{"color-space":"srgb","components":{"alpha":"1.000","blue":"0xE0","green":"0x64","red":"0x00"}},"idiom":"universal"},
     {"appearances":[{"appearance":"luminosity","value":"dark"}],"color":{"color-space":"srgb","components":{"alpha":"1.000","blue":"0xFA","green":"0xA5","red":"0x47"}},"idiom":"universal"}],
     "info":{"author":"xcode","version":1}}
    """#, "\(accent)/Contents.json")

    // Previews
    let prev = dir("previews")
    save(cg(PhoneChrome(dark: false) { LaunchScreenPreview(dark: false) }, scale: 2), "\(prev)/launch-screen-light.png")
    save(cg(PhoneChrome(dark: true) { LaunchScreenPreview(dark: true) }, scale: 2), "\(prev)/launch-screen-dark.png")
    save(cg(IconSheet(), scale: 1), "\(prev)/app-icon-sheet.png")

    // Launch film cards (1920 x 1080) and overlays (transparent)
    let film = dir("film")
    for (name, view) in FilmCards.all { save(cg(view, scale: 1), "\(film)/\(name).png") }
}

/// The icon at home-screen sizes, masked like iOS does, in light / dark / tinted, for review.
struct IconSheet: View {
    var body: some View {
        HStack(spacing: 60) {
            ForEach(Array([("Light", AppIconArt.Variant.light, Color(hex: 0xDCE6F5)), ("Dark", .dark, Color(hex: 0x111111)),
                           ("Tinted", .tinted, Color(hex: 0x1B1F2A))].enumerated()), id: \.offset) { _, v in
                VStack(spacing: 18) {
                    ZStack {
                        if v.1 == .dark { Color(hex: 0x1C1C1E) }
                        if v.1 == .tinted { Color(hex: 0x23314A) }
                        AppIconArt(v.1).scaleEffect(0.25).frame(width: 256, height: 256)
                    }
                    .frame(width: 256, height: 256)
                    .clipShape(RoundedRectangle(cornerRadius: 57, style: .continuous))
                    HStack(spacing: 24) {
                        ForEach([120, 60, 40], id: \.self) { s in
                            ZStack {
                                if v.1 == .dark { Color(hex: 0x1C1C1E) }
                                if v.1 == .tinted { Color(hex: 0x23314A) }
                                AppIconArt(v.1).scaleEffect(CGFloat(s) / 1024).frame(width: CGFloat(s), height: CGFloat(s))
                            }
                            .frame(width: CGFloat(s), height: CGFloat(s))
                            .clipShape(RoundedRectangle(cornerRadius: CGFloat(s) * 0.2237, style: .continuous))
                        }
                    }
                    Text(v.0).font(.system(size: 22, weight: .semibold)).foregroundStyle(v.1 == .light ? Color.black : Color.white)
                }
                .padding(40)
                .background(v.2, in: RoundedRectangle(cornerRadius: 30))
            }
        }
        .padding(50)
        .background(Color.white)
    }
}
