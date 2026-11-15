# Changelog

Notable changes to ULTRON (formerly J.A.R.V.I.S.). Day-by-day detail is in [docs/BUILD_LOG.md](docs/BUILD_LOG.md).

## [Unreleased]

### Changed
- Repository cleanup with no change in behaviour: code moved to `src/ultron/` (start with `run_ultron.bat` or `python -m ultron`), editable data in `config/`, dependencies pinned in `pyproject.toml`, `commands.txt` became `docs/COMMANDS.md`, new README and architecture notes, CI on GitHub Actions.
- Removed dead code, the old `examples/` folder, the SAPI voice unlock scripts and the unused speech libraries.

### Added
- `python -m ultron --self-test` (no microphone, speaker or models needed).
- Command registry with three-stage understanding (rules, meaning matcher, LLM tool calls); default LLM `qwen2.5:3b` on 4 GB GPUs.
- Hardware profiles, window control, voice interruption (barge-in), conversation memory, the activity log, streamed and honest AI answers.
- Renamed from JARVIS to ULTRON.

## [1.1.0] - 2026-06-26

- Cross-platform commands, central logging, microphone and Ollama resilience, `.env` settings.

## [1.0.0] - 2026-06-25

- Piper neural voice, Faster-Whisper, openWakeWord ("Hey Jarvis"), 40+ voice commands, boot and sleep sounds.
