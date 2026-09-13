import Foundation
import Speech
import AVFoundation

/// Pure helpers for speech locale + permission messaging (unit-testable).
enum VoiceAskSupport {
    /// Map app locales (`en`, `zh-Hans`, …) onto an `SFSpeechRecognizer`-supported locale.
    /// Does **not** consult `isAvailable` — that is false until speech is authorized.
    static func resolvedSpeechLocale(
        from locale: Locale,
        supported: Set<Locale> = SFSpeechRecognizer.supportedLocales()
    ) -> Locale {
        let preferred = [
            locale.identifier,
            locale.language.languageCode.map { "\($0.identifier)-\(locale.region?.identifier ?? "US")" },
            locale.language.languageCode?.identifier,
        ].compactMap { $0 }

        for id in preferred {
            let candidate = Locale(identifier: id)
            if supported.contains(where: { $0.identifier == candidate.identifier }) {
                return candidate
            }
        }

        let lang = locale.language.languageCode?.identifier ?? "en"
        if let match = supported.first(where: {
            $0.language.languageCode?.identifier == lang
        }) {
            return match
        }
        if let enUS = supported.first(where: { $0.identifier == "en-US" }) {
            return enUS
        }
        return Locale(identifier: "en-US")
    }

    static func speechAuthMessage(_ status: SFSpeechRecognizerAuthorizationStatus) -> String? {
        switch status {
        case .authorized:
            return nil
        case .denied:
            return "Speech recognition is off. Enable it in Settings → BSH Research → Speech Recognition."
        case .restricted:
            return "Speech recognition is restricted on this device (Screen Time / MDM)."
        case .notDetermined:
            return "Speech recognition permission wasn’t granted."
        @unknown default:
            return "Speech recognition not authorized (status \(status.rawValue))."
        }
    }

    static func joinCommitted(_ prefix: String, piece: String) -> String {
        let a = prefix.trimmingCharacters(in: .whitespacesAndNewlines)
        let b = piece.trimmingCharacters(in: .whitespacesAndNewlines)
        if a.isEmpty { return b }
        if b.isEmpty { return a }
        return a + " " + b
    }

    /// Whether a recognition-task NSError should be treated as a quiet restart.
    static func isRetryableRecognitionError(_ error: NSError) -> Bool {
        if error.domain == NSURLErrorDomain, error.code == NSURLErrorCancelled { return true }
        // 216 = cancelled by client; 1110 = no speech; 1101 = retry; 203 = restricted/retry
        if error.code == 216 { return true }
        if error.domain == "kAFAssistantErrorDomain" {
            return [1110, 1101, 203, 1700].contains(error.code)
        }
        return false
    }
}

@MainActor
final class VoiceAskController: ObservableObject {
    @Published var isListening = false
    @Published var transcript = ""
    /// Exact failure string — always surfaced in the Copilot UI banner.
    @Published var error: String?
    @Published var statusLine: String?

    private var recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let engine = AVAudioEngine()
    private var wantsListening = false
    private var sessionID = UUID()
    private var tapInstalled = false
    private var committed = ""
    private var pendingLocale = Locale(identifier: "en-US")

    func toggle(locale: Locale = Locale(identifier: "en-US")) {
        if isListening || wantsListening {
            stop()
        } else {
            start(locale: locale)
        }
    }

    func start(locale: Locale) {
        error = nil
        transcript = ""
        committed = ""
        wantsListening = true
        pendingLocale = locale
        statusLine = "Requesting microphone & speech permission…"

        // CRITICAL: never gate on `isAvailable` before authorization.
        // Before the user grants Speech Recognition, `isAvailable` is often
        // false and would abort without ever showing the system prompts.
        requestMicrophoneThenSpeech { [weak self] ok, message in
            guard let self else { return }
            guard self.wantsListening else { return }
            guard ok else {
                self.fail(message ?? "Permission denied.")
                return
            }
            self.beginSession(locale: self.pendingLocale)
        }
    }

    func stop() {
        wantsListening = false
        sessionID = UUID()
        statusLine = nil
        teardownEngine(cancelTask: true)
        isListening = false
    }

    // MARK: - Permissions

    private func requestMicrophoneThenSpeech(_ completion: @escaping (Bool, String?) -> Void) {
        let finish: (Bool, String?) -> Void = { ok, message in
            Task { @MainActor in
                completion(ok, message)
            }
        }

        // Prefer the classic AVAudioSession API — it reliably triggers the
        // mic TCC prompt on first tap on iOS 17–26 device builds.
        AVAudioSession.sharedInstance().requestRecordPermission { micGranted in
            guard micGranted else {
                finish(false, "Microphone access is off. Enable it in Settings → BSH Research → Microphone.")
                return
            }
            SFSpeechRecognizer.requestAuthorization { status in
                if let message = VoiceAskSupport.speechAuthMessage(status) {
                    finish(false, message)
                } else {
                    finish(true, nil)
                }
            }
        }
    }

    // MARK: - Session

    private func beginSession(locale: Locale) {
        teardownEngine(cancelTask: true)

        let speechLocale = VoiceAskSupport.resolvedSpeechLocale(from: locale)
        let recognizer = SFSpeechRecognizer(locale: speechLocale)
        guard let recognizer else {
            fail("No speech recognizer for \(speechLocale.identifier). Try English in Settings.")
            return
        }
        // Only now — after authorization — is `isAvailable` meaningful.
        guard recognizer.isAvailable else {
            fail(
                "Speech recognition isn’t available right now for \(speechLocale.identifier). "
                    + "Check network (Apple speech servers) or try again in a moment."
            )
            return
        }
        self.recognizer = recognizer
        statusLine = "Listening… (\(speechLocale.identifier))"

        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(
                .playAndRecord,
                mode: .measurement,
                options: [.duckOthers, .defaultToSpeaker, .allowBluetooth]
            )
            try session.setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            fail("Audio session: \(error.localizedDescription)")
            return
        }

        let input = engine.inputNode
        // Use nil format so the tap matches the hardware input format exactly.
        // Passing a mismatched format is a common on-device silent failure.
        let hwFormat = input.outputFormat(forBus: 0)
        guard hwFormat.sampleRate > 0, hwFormat.channelCount > 0 else {
            fail("Microphone isn’t ready (sampleRate=\(hwFormat.sampleRate)). Try again.")
            return
        }

        input.installTap(onBus: 0, bufferSize: 1024, format: hwFormat) { [weak self] buffer, _ in
            self?.request?.append(buffer)
        }
        tapInstalled = true

        do {
            engine.prepare()
            try engine.start()
        } catch {
            teardownEngine(cancelTask: true)
            fail("Audio engine: \(error.localizedDescription)")
            return
        }

        isListening = true
        startRecognitionTask()
    }

    private func startRecognitionTask() {
        guard wantsListening, let recognizer else { return }

        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        req.taskHint = .dictation
        // Network / Apple servers — do NOT require on-device models or the
        // Speech Recognition entitlement capability.
        if #available(iOS 13, *) {
            req.requiresOnDeviceRecognition = false
        }
        request = req

        let id = UUID()
        sessionID = id

        task = recognizer.recognitionTask(with: req) { [weak self] result, err in
            Task { @MainActor in
                guard let self, self.sessionID == id else { return }

                if let result {
                    let piece = result.bestTranscription.formattedString
                    self.transcript = VoiceAskSupport.joinCommitted(self.committed, piece: piece)
                    if result.isFinal {
                        self.committed = self.transcript
                        self.finishCurrentRequest()
                        if self.wantsListening {
                            self.startRecognitionTask()
                        }
                        return
                    }
                }

                guard let err else { return }
                let ns = err as NSError
                self.finishCurrentRequest()

                if VoiceAskSupport.isRetryableRecognitionError(ns) {
                    guard self.wantsListening else { return }
                    // Brief pause so we don't tight-loop on "no speech".
                    Task { @MainActor in
                        try? await Task.sleep(nanoseconds: 250_000_000)
                        guard self.wantsListening else { return }
                        self.startRecognitionTask()
                    }
                    return
                }

                if self.wantsListening {
                    self.fail(
                        "Recognition error [\(ns.domain) \(ns.code)]: \(ns.localizedDescription)"
                    )
                }
            }
        }
    }

    private func finishCurrentRequest() {
        task = nil
        request?.endAudio()
        request = nil
    }

    private func fail(_ message: String) {
        error = message
        statusLine = nil
        wantsListening = false
        sessionID = UUID()
        teardownEngine(cancelTask: true)
        isListening = false
    }

    private func teardownEngine(cancelTask: Bool) {
        if cancelTask {
            task?.cancel()
        }
        task = nil
        request?.endAudio()
        request = nil

        if engine.isRunning {
            engine.stop()
        }
        if tapInstalled {
            engine.inputNode.removeTap(onBus: 0)
            tapInstalled = false
        }

        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
}
