# Changelog

All notable changes to the ULTRON desktop assistant project (formerly J.A.R.V.I.S.) will be documented in this file.

## [Unreleased]

### Changed
- Renamed the assistant from JARVIS to ULTRON: new name, personality, prompts, greetings and file names (ultron.py, download_voice.py, ultron.log). Wake phrase stays "Hey Jarvis" until a custom "Hey Ultron" model exists.

---

## [1.1.0] - 2026-06-26

### Added
- **Multi-Platform Portability Support**: Replaced Windows-only library calls with generic cross-platform commands supporting Windows, macOS, and Linux.
- **Centralized Logging System**: Replaced raw `print` statements with a centralized `logger.py` framework recording detailed logs to a rotating `jarvis.log` file.
- **Microphone & Server Resilience**: Standby loop now checks and retries audio stream initialization gracefully upon missing hardware, and verifies local Ollama model presence at startup.
- **Environment Configurations**: Implemented `.env.example` and dynamic loading of settings in `config.py`.

### Refactored
- Cleaned up root directory by moving legacy scripts and test files into the `examples/` directory.

---

## [1.0.0] - 2026-06-25

### Added
- Neural Text-to-Speech (Piper ONNX) and speech recognition (Faster-Whisper).
- Local OpenWakeWord detector loop monitoring for *"Hey Jarvis"*.
- 40+ built-in system, developer, Git, and utility voice commands.
- Premium synthesized repulsor boot sounds and sleep standby power-down chimes.
