# Changelog

Notable changes to ULTRON (formerly J.A.R.V.I.S.). Day-by-day detail is in [docs/BUILD_LOG.md](docs/BUILD_LOG.md).

## [Unreleased]

### Fixed
- Silence is no longer sent to Whisper; a conversation with no speech for 45 s (`CONVERSATION_IDLE_SECONDS`) goes back to the wake word.
- Closing an app is announced only when it may hold unsaved work, and never says both "Closing" and "Closed".
- Whisper retries are off by default (`WHISPER_TEMPERATURE_FALLBACK`); low-confidence transcriptions, AI replies and tool calls are logged.
- Opening a browser or app waits until the reply is audible, so the voice is not delayed.

### Changed
- Repository cleanup with no change in behaviour: code moved to `src/ultron/` (start with `run_ultron.bat` or `python -m ultron`), editable data in `config/`, dependencies pinned in `pyproject.toml`, `commands.txt` became `docs/COMMANDS.md`, new README and architecture notes, CI on GitHub Actions.
- Removed dead code, the old `examples/` folder, the SAPI voice unlock scripts and the unused speech libraries.

### Added
- Voice effect chain (`VOICE_PRESET`, `VOICE_PITCH`, `VOICE_METAL`, `VOICE_REVERB`, `VOICE_DOUBLE`), `VOICE_MODEL`, candidate voices via `tools/download_voice.py`, `tools/voice_samples.py`. `VOICE_SPEED` now defaults to 0.9.
- `python -m ultron --self-test` (no microphone, speaker or models needed).
- Command registry with three-stage understanding (rules, meaning matcher, LLM tool calls); default LLM `qwen2.5:3b` on 4 GB GPUs.
- Hardware profiles, window control, voice interruption (barge-in), conversation memory, the activity log, streamed and honest AI answers.
- Renamed from JARVIS to ULTRON.

## [1.1.0] - 2026-06-26

- Cross-platform commands, central logging, microphone and Ollama resilience, `.env` settings.

## [1.0.0] - 2026-06-25

- Piper neural voice, Faster-Whisper, openWakeWord ("Hey Jarvis"), 40+ voice commands, boot and sleep sounds.
