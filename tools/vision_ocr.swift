// tools/vision_ocr.swift — on-device OCR helper (macOS Vision framework).
//
// WHY THIS EXISTS
//   lgwks is local-first and never egresses document bytes to a cloud OCR/LLM.
//   The canonical OCR port (lgwks_input._ocr_image_bytes) resolves a backend
//   chain: tesseract (if installed) -> this macOS Vision helper -> give up.
//   Vision ships with the OS, so on Apple platforms this gives high-fidelity,
//   zero-dependency, zero-egress OCR with no `brew install` and no model
//   download. On non-Apple platforms this binary is simply absent and the port
//   degrades to "" (current behaviour) — the product stays portable.
//
// CONTRACT (stable, do not change without bumping the call site)
//   argv[1]            image file path (PNG/JPEG/GIF/WEBP/BMP/TIFF). Required.
//   env LGWKS_OCR_LANGS  comma-separated BCP-47 tags, e.g. "en-US,fr-CA".
//                        default: "en-US".
//   stdout             recognized lines, top candidate per observation, "\n"-joined.
//   exit 0             success (stdout may be empty if the image had no text).
//   exit 2             usage error (no path).
//   exit 3             image could not be loaded/decoded.
//   exit 4             Vision request failed to perform.
//
// This file is compiled lazily to a cached binary by lgwks_input._vision_binary()
// (keyed on a hash of these bytes), so the ~one-time swiftc cost is paid only on
// first use or when this source changes — repeated calls are pure inference.

import Foundation
import ImageIO
import Vision
import CoreGraphics

func langs() -> [String] {
    let raw = ProcessInfo.processInfo.environment["LGWKS_OCR_LANGS"] ?? "en-US"
    let tags = raw.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }
    return tags.filter { !$0.isEmpty } ?? ["en-US"]
}

let args = CommandLine.arguments
guard args.count >= 2, !args[1].isEmpty else {
    FileHandle.standardError.write("usage: vision_ocr <image>\n".data(using: .utf8)!)
    exit(2)
}

let cfURL = URL(fileURLWithPath: args[1]) as CFURL
guard let src = CGImageSourceCreateWithURL(cfURL, nil),
      let cgImage = CGImageSourceCreateImageAtIndex(src, 0, nil) else {
    FileHandle.standardError.write("error: cannot decode image\n".data(using: .utf8)!)
    exit(3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = langs()

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("error: vision perform failed: \(error)\n".data(using: .utf8)!)
    exit(4)
}

let lines = (request.results ?? []).compactMap { obs -> String? in
    obs.topCandidates(1).first?.string
}
FileHandle.standardOutput.write(lines.joined(separator: "\n").data(using: .utf8)!)
FileHandle.standardOutput.write("\n".data(using: .utf8)!)
