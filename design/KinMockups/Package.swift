// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "KinMockups",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "KinDesign", targets: ["KinDesign"])],
    targets: [
        .target(name: "KinDesign"),
        .executableTarget(name: "KinRender", dependencies: ["KinDesign"]),
    ]
)
