# ULTRON: context for Claude sessions

Read this first in every new session. It holds the project context so a fresh session can continue without the old chat. Full design, decisions (D1 to D22) and journal: docs/BUILD_LOG.md.

## Session handoff rule (from the user)
When a session's context reaches about 30 to 40 percent full, stop at a clean point and:
1. Update the "Progress log" and "Next steps" sections below so they are accurate.
2. Commit CLAUDE.md on the working branch.
3. Start a new session that begins by reading this file, and continue there.
Do not wait until the context is nearly full.

## Project
Name: ULTRON (renamed from JARVIS on 2026-11-15). Repo: https://github.com/twarangupta/U.L.T.R.O.N (renamed from J.A.R.V.I.S on 2026-11-15; origin already points here). Local folder keeps its old name J.A.R.V.I.S-main.
Goal: free, local, hands-free voice assistant that controls the PC, feels instant (under 1 s for simple commands), installs with one click, runs on 8 GB laptops, saves memory by picking smaller models (never by unloading models between commands).
Planning files (user's Downloads): JARVIS_project_brief.md, JARVIS_handover_prompt.md, JARVIS_improvements.xlsx (41 items).
Feasibility report: https://claude.ai/artifact/KNc9WgT4fuh7xvwf6EB282

## Owner's mandate (2026-11-15)
Organize the code neatly and human-readably, remove unnecessary code, change or delete code freely, add plenty of CI. End result: a fully functional, tested Windows installer (UltronSetup.exe). See BUILD_LOG D22.

## Working rules
- Work on feature branches off p1-fixes (integration branch), never on main. Merge into p1-fixes after the user tests; p1-fixes goes to main by PR.
- Small, reviewable commits with honest messages.
- Code deletion on branches is approved (D22). Still ask before pushing, merging to main, rewriting history, or anything on GitHub.
- After each change, explain it in plain words and say how to test it on the laptop.
- Writing style for the user: plain text, no em dashes, light markup.
- For large changes, describe the plan before writing code.
- When something is ambiguous, ask; otherwise pick a sensible default and say which.
- Proactively suggest improvements, hacks, tricks, risks and feature ideas (short "Tips" in step reports).
- Persona: blunt, dry, condescending about human habits, occasional jokes, always does the task, no "sir". All persona lines in persona.py, original writing only.
- commands.txt is the living list of voice commands. Update it in the same commit whenever a command is added, removed or its phrases change.
- Add a journal entry to docs/BUILD_LOG.md section 19 after each branch; keep it 20 to 30 pages.

## Current code (feat/rename-ultron plus the two branches below)
- ultron.py: main loop. Wake word, record, transcribe() (Whisper beam_size=5), execute_command(text, confirm), else LLM. Parses "COMMAND:" tags with a regex. On fix/command-safety: ask_confirmation() (speak prompt, listen 6 s, only "confirm" passes), is_sleep_phrase() exact after normalize.
- persona.py: ULTRON lines (greetings, wake, sleep, goodbye, quips, CONFIRM_PROMPTS, CANCELLED_REPLIES), maybe_quip() with ULTRON_QUIP_RATE (0.15).
- wakeword.py + config.py: wake phrase DECIDED: custom "Hey Ultron" openWakeWord model (user trains it in Colab, docs/WAKE_WORD_TRAINING.md). On feat/hey-ultron-wakeword: uses models/hey_ultron.onnx if present, else hey_jarvis with a log warning; WAKE_PHRASE for log lines; WAKE_WORD_MODEL env overrides. Threshold still 0.2 (tune/wake-threshold sets 0.5).
- audio.py: PyAudio, stream opened/closed between modes, amplitude > 500 with 0.8 s silence. record_phrase(max_seconds=...).
- brain.py: Ollama llama3.2:3b, non-streaming, full history.
- speaker.py: Piper models/ultron-voice.onnx (falls back to jarvis-high.onnx), full synthesis before playing.
- commands/ (on fix/command-safety): __init__.execute_command order is typing (general.execute_typing_command, regex) -> risky.py (shutdown, restart, empty recycle bin: fullmatch on normalized text + confirm callback; no callback = cancel) -> system, git_helpers, developer, general. text.normalize() strips punctuation and fillers. Other substring matches remain (e.g. "pause" anywhere) until the command registry.
- git_organic_committer.py: deleted on fix/command-safety.
- requirements.txt: >= versions, pyaudio and sounddevice both listed.

## Branches
p1-fixes (integration) now contains feat/rename-ultron, fix/command-safety and feat/hey-ultron-wakeword (merged 2026-11-15 at the user's request, before laptop testing). The user should test p1-fixes once; fixes go on new branches.
Waiting branches were moved onto p1-fixes (they had no commits of their own): feat/timing-log, tune/wake-threshold, perf/whisper-settings, feat/sounddevice-mic, feat/silero-vad, feat/streaming-llm-tts, feat/quick-replies-followup, test/phrase-suite, build/windows-installer. Start each from the latest p1-fixes.
main gets p1-fixes through a GitHub pull request once phase 1 is tested on the laptop (needs the user's go-ahead to push). The user cancelled the local folder rename.

## Progress log
- 2026-11-15: Zip folder turned into a git repo linked to origin; branch p1-fixes; CLAUDE.md; docs/BUILD_LOG.md; feature branches created.
- 2026-11-15: feat/rename-ultron: JARVIS to ULTRON everywhere, persona.py, ~90 "sir" removed from replies, new system prompt, docs and commands.txt renamed.
- 2026-11-15: fix/command-safety: whole-phrase risky commands with spoken confirm, typing first, exact sleep phrase, fake-history script deleted.
- 2026-11-15: feat/hey-ultron-wakeword: training guide and model wiring with fallback. User is training the model.

## Next steps (in order)
1. User tests feat/rename-ultron, fix/command-safety and feat/hey-ultron-wakeword, then merges them into p1-fixes (ask before merging).
2. feat/timing-log (timing.py, one line per command), then tune/wake-threshold (0.5, custom model), perf/whisper-settings (beam 1, no timestamps, condition_on_previous_text False).
3. feat/sounddevice-mic (one stream, ring buffer), feat/silero-vad (0.4 s).
4. feat/streaming-llm-tts (warm model, sentence streaming), feat/quick-replies-followup.
5. Cleanup and restructure: src/ultron package, command registry, remove dead code (pyttsx3, SAPI unlock scripts, SpeechRecognition, examples), pinned deps, pyproject.toml, config in %APPDATA%.
6. test/phrase-suite plus CI: ruff, pytest, Windows build.
7. build/windows-installer: llama.cpp server bundle, bundle hey_ultron.onnx (check licences), tray, first-run wizard, PyInstaller + Inno Setup, GitHub Actions release with silent-install smoke test.
