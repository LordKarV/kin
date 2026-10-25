// syscap: capture system audio (the other side of a Zoom / Meet call) with ScreenCaptureKit and write
// 16 kHz mono PCM16 little-endian to stdout. Logs go to stderr. The Electron overlay spawns this and
// forwards the bytes to KIN's /ws/call socket as the grandparent leg.
//
// Usage: syscap [bundle.id ...]   no args = all system audio; with args = only those apps
//        (e.g. us.zoom.xos com.google.Chrome), which keeps notification sounds out of the transcript.
// Needs the Screen Recording permission (System Settings > Privacy & Security), like Cluely and Granola.
import CoreMedia
import Foundation
import ScreenCaptureKit

func log(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

final class Capture: NSObject, SCStreamOutput, SCStreamDelegate {
    private var stream: SCStream?
    private var loggedFormat = false

    func start(bundleIDs: [String]) async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else { throw NSError(domain: "syscap", code: 1, userInfo: [NSLocalizedDescriptionKey: "no display"]) }
        let filter: SCContentFilter
        if bundleIDs.isEmpty {
            filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        } else {
            let apps = content.applications.filter { bundleIDs.contains($0.bundleIdentifier) }
            log("syscap: capturing apps \(apps.map(\.bundleIdentifier)) (asked for \(bundleIDs))")
            filter = SCContentFilter(display: display, including: apps, exceptingWindows: [])
        }
        let cfg = SCStreamConfiguration()
        cfg.capturesAudio = true
        cfg.sampleRate = 16000
        cfg.channelCount = 1
        cfg.excludesCurrentProcessAudio = true
        // ponytail: SCK always streams video too; make it 2x2 at 1 fps so it costs nothing
        cfg.width = 2
        cfg.height = 2
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        let s = SCStream(filter: filter, configuration: cfg, delegate: self)
        try s.addStreamOutput(self, type: .audio, sampleHandlerQueue: DispatchQueue(label: "syscap.audio"))
        try s.addStreamOutput(self, type: .screen, sampleHandlerQueue: DispatchQueue(label: "syscap.screen"))
        try await s.startCapture()
        stream = s
        log("syscap: started")
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sb.isValid else { return }
        if !loggedFormat, let fd = sb.formatDescription, let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fd)?.pointee {
            log("syscap: format \(asbd.mSampleRate) Hz, \(asbd.mChannelsPerFrame) ch, \(asbd.mBitsPerChannel) bit, flags \(asbd.mFormatFlags)")
            loggedFormat = true
        }
        var block: CMBlockBuffer?
        var abl = AudioBufferList()
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sb, bufferListSizeNeededOut: nil, bufferListOut: &abl, bufferListSize: MemoryLayout<AudioBufferList>.size,
            blockBufferAllocator: nil, blockBufferMemoryAllocator: nil, flags: 0, blockBufferOut: &block)
        guard status == noErr, let raw = abl.mBuffers.mData else { return }
        // SCK delivers Float32; channelCount = 1 means a single buffer
        let n = Int(abl.mBuffers.mDataByteSize) / MemoryLayout<Float32>.size
        let f = raw.bindMemory(to: Float32.self, capacity: n)
        var pcm = [Int16](repeating: 0, count: n)
        for i in 0..<n { pcm[i] = Int16(max(-1, min(1, f[i])) * 32767) }
        pcm.withUnsafeBytes { FileHandle.standardOutput.write(Data($0)) }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        log("syscap: stopped: \(error.localizedDescription)")
        exit(2)
    }
}

let capture = Capture()
signal(SIGPIPE, SIG_IGN)  // parent closed the pipe: write fails, we exit below instead of crashing
Task {
    do {
        try await capture.start(bundleIDs: Array(CommandLine.arguments.dropFirst()))
    } catch {
        log("syscap: failed to start: \(error.localizedDescription) (grant Screen Recording permission?)")
        exit(1)
    }
}
// exit when the parent goes away (stdin closes)
DispatchQueue.global().async {
    while FileHandle.standardInput.availableData.count > 0 {}
    exit(0)
}
dispatchMain()
