# ULTRON: context for Claude sessions

Read this first in every new session. It holds the project context so a fresh session can continue without the old chat. Full design, decisions (D1 to D22) and journal: docs/BUILD_LOG.md.

## Session handoff rule (from the user)
When a session's context reaches about 30 to 40 percent full, stop at a clean point and:
1. Update the "Progress log" and "Next steps" sections below so they are accurate.
2. Commit CLAUDE.md on the working branch.
3. Start a new session that begins by reading this file, and continue there.
Do not wait until the context is nearly full.

## Project
Name: ULTRON (renamed from JARVIS on 2026-11-15). Repo: https://github.com/twarangupta/J.A.R.V.I.S (owner may rename it to U.L.T.R.O.N on GitHub; then run git remote set-url).
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

## Current code (after feat/rename-ultron)
- ultron.py: main loop. Wake word, record, Whisper (beam_size=5), execute_command, else LLM. Parses "COMMAND:" tags with a regex. Sleep phrase by substring.
- persona.py: ULTRON lines (greetings, wake, sleep, goodbye, quips), maybe_quip() with ULTRON_QUIP_RATE (0.15).
- wakeword.py: openWakeWord "hey_jarvis" (only built-in model), threshold 0.2. Wake phrase decision pending: train "hey ultron" or switch to sherpa-onnx keywords.
- audio.py: PyAudio, stream opened/closed between modes, amplitude > 500 with 0.8 s silence.
- brain.py: Ollama llama3.2:3b, non-streaming, full history.
- config.py: env settings, ULTRON system prompt with [COMMAND: x] routing.
- speaker.py: Piper models/ultron-voice.onnx (falls back to jarvis-high.onnx), full synthesis before playing.
- commands/: system, git_helpers, developer, general, checked in that order. Bugs: substring shutdown/restart (system.py ~198, ~208), recycle bin no confirm (~388), typing checked last (general.py).
- git_organic_committer.py: fabricated history script. Delete (approved under D22).
- requirements.txt: >= versions, pyaudio and sounddevice both listed.

## Branches
p1-fixes (integration). Done: feat/rename-ultron (not merged yet, awaiting user test).
Waiting: feat/timing-log, fix/command-safety, tune/wake-threshold, perf/whisper-settings, feat/sounddevice-mic, feat/silero-vad, feat/streaming-llm-tts, feat/quick-replies-followup, test/phrase-suite, build/windows-installer. All were created before the rename; update each from p1-fixes before starting it.

## Progress log
- 2026-11-15: Zip folder turned into a git repo linked to origin; branch p1-fixes; CLAUDE.md; docs/BUILD_LOG.md; feature branches created.
- 2026-11-15: feat/rename-ultron: JARVIS to ULTRON everywhere, persona.py, ~90 "sir" removed from replies, new system prompt, docs and commands.txt renamed.

## Next steps (in order)
1. User tests feat/rename-ultron, then merge it into p1-fixes.
2. fix/command-safety (whole-phrase match, voice confirm, typing first, sleep phrase exact) and delete git_organic_committer.py.
3. feat/timing-log, tune/wake-threshold (0.5), perf/whisper-settings (beam 1, no timestamps).
4. feat/sounddevice-mic (one stream, ring buffer), feat/silero-vad (0.4 s).
5. feat/streaming-llm-tts (warm model, sentence streaming), feat/quick-replies-followup.
6. Cleanup and restructure: src/ultron package, command registry, remove dead code (pyttsx3, SAPI unlock scripts, SpeechRecognition, examples), pinned deps, pyproject.toml, config in %APPDATA%.
7. test/phrase-suite plus CI: ruff, pytest, Windows build.
8. build/windows-installer: llama.cpp server bundle, tray, first-run wizard, PyInstaller + Inno Setup, GitHub Actions release with silent-install smoke test.
