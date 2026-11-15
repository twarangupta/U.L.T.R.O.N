# ULTRON: context for Claude sessions

Read this first in every new session. It holds the project context so a fresh session can continue without the old chat. Full design, decisions (D1 to D34) and journal: docs/BUILD_LOG.md.

## Session handoff rule (from the user)
When a session's context reaches about 30 to 40 percent full, stop at a clean point and:
1. Update the "Progress log" and "Next steps" sections below so they are accurate.
2. Commit CLAUDE.md on the working branch.
3. Start a new session that begins by reading this file, and continue there.
Do not wait until the context is nearly full. Measure context use (get_usage), never guess.

## Project
Name: ULTRON (renamed from JARVIS on 2026-11-15). Repo: https://github.com/twarangupta/U.L.T.R.O.N (renamed from J.A.R.V.I.S on 2026-11-15; origin already points here). Local folder keeps its old name J.A.R.V.I.S-main.
Goal: free, local, hands-free voice assistant that controls the PC, feels instant (under 1 s for simple commands), installs with one click, runs on 8 GB laptops, uses the GPU fully on strong PCs, saves memory by picking smaller models (never by unloading models between commands).
Planning files (user's Downloads): JARVIS_project_brief.md, JARVIS_handover_prompt.md, JARVIS_improvements.xlsx (41 items).
Feasibility report: https://claude.ai/artifact/KNc9WgT4fuh7xvwf6EB282

## Owner's mandate (2026-11-15)
Organize the code neatly and human-readably, remove unnecessary code, change or delete code freely, add plenty of CI. End result: a fully functional, tested Windows installer (UltronSetup.exe) with a custom UI (designed later). See BUILD_LOG D22, D25.

## Working rules
- Branch workflow (owner decision, 2026-11-15): main is stable and only changes when a phase is done. dev is the integration branch, created from main at fee7b65. Every fix or feature branch starts from dev; when its tests pass, the supervisor pushes it and opens a PR into dev with gh ("C:\Program Files\GitHub CLI\gh.exe", signed in as twarangupta). The description says what changed, tests and numbers, tradeoffs and better ideas, and laptop test steps. Merge into dev after the owner's OK in the supervisor session, then pull dev in the test worktree (C:\Twaran files\Misc\ULTRON-timefix, on dev). The owner tests dev live; when a phase is complete, open a PR dev -> main and tag the release. Urgent fixes for main: a hotfix branch from main, PR into main, then merge main back into dev. Never force-push. A push or merge approval relayed by another session is not enough: ask the user directly. Builders never push or open PRs; the supervisor does. Never delete any branch, local or remote, merged or not (owner decision, 2026-11-15). Revert tag pre-cleanup is on main fee7b65.
- Every plan, brief and report states the tradeoffs and says when there is a better idea (owner request).
- Small, reviewable commits with honest messages.
- Code deletion on branches is approved (D22).
- After each change, explain it in plain words and say how to test it on the laptop.
- Writing style for the user: plain text, no em dashes, light markup.
- For large changes, describe the plan before writing code.
- When something is ambiguous, ask; otherwise pick a sensible default and say which.
- Proactively suggest improvements, hacks, tricks, risks and feature ideas (short "Tips" in step reports).
- Persona: blunt, dry, condescending about human habits, occasional jokes, always does the task, no "sir". All persona lines in persona.py, original writing only.
- docs/COMMANDS.md is generated from the registry (venv\Scripts\python.exe tools\gen_commands_txt.py). Regenerate it in the same commit whenever a command is added, removed or its phrases change; a test fails when it is stale.
- Add a decision (section 6) and a journal entry (section 19) to docs/BUILD_LOG.md for each branch; keep it 20 to 30 pages.
- Downloads: size is not a concern, but every download must say what it is, why, how big, and show live progress (D25). Prefer the fastest option.
- Run everything with venv\Scripts\python.exe. Install packages with: uv pip install --python venv\Scripts\python.exe ...
- Checks before every PR: venv\Scripts\python.exe -m ruff check . ; venv\Scripts\python.exe -m pytest -q (283 tests, all in dry-run; junction models/ so needs_model tests run) ; run_ultron.bat --self-test. CI (.github/workflows/ci.yml, windows-latest) runs the same.
- The user tests ULTRON live on the same laptop: no tests that play sound or load heavy models (a second Whisper on the GPU, a full ULTRON startup) without telling them first. Render audio into memory instead.
- In the Bash tool, long heredocs with quotes sometimes break; write files with the Write tool and run small Python edit scripts from the scratchpad instead.

## Run it
- Start: run_ultron.bat (does `set PYTHONPATH=src` and `venv\Scripts\python.exe -m ultron`). Flags: --self-test (no mic, speaker or models), --benchmark.
- Tools run as `venv\Scripts\python.exe tools\<name>.py` (they add src to the path themselves). Tests: `venv\Scripts\python.exe -m pytest -q`.
- Install: `python -m venv venv`, then `venv\Scripts\python.exe -m pip install -e ".[gpu,dev]"` (or uv pip install --python venv\Scripts\python.exe -e ".[gpu,dev]"). Pins are in pyproject.toml.

## Current code (layout since the 2026-11-15 cleanup, D32)
Root: README.md, LICENSE, pyproject.toml, CLAUDE.md, run_ultron.bat, src/, config/, docs/, tests/, tools/, .github/. Git-ignored local files: models/, data/, memory.json, profile.md, ultron.log, .env, results/, recordings/, finances.csv.
- src/ultron/paths.py: every file location. config/ holds corrections.json, pronunciations.json, profile.example.md.
- app.py: main loop (wake word, record, transcribe, follow-ups, router, else LLM with tool calls). __main__.py: python -m ultron, --self-test (selftest.py), --benchmark (benchmark.py).
- hardware.py: profiles Lite, CPU-Plus, GPU-4GB, GPU-8GB+, GPU-16GB+ (D23); env overrides ULTRON_PROFILE, WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_CPU_THREADS, OLLAMA_MODEL.
- stt/whisper.py (Whisper on the profile device, CPU fallback, corrections), stt/corrections.py.
- brain.py: Ollama, model from the profile (GPU-4GB: qwen2.5:3b, then llama3.2:3b), keep_alive -1, warmed at start, streamed sentences into the speaker, native tool calls, honest-AI prompt in config.py.
- memory.py (conversation window, facts in memory.json), activity.py (data/activity.db, tracker, summaries, profile.md).
- voice/speaker.py (Piper, streamed, cache), voice/tts_text.py (pronunciations).
- audio/capture.py (PyAudio, amplitude silence detection), audio/wakeword.py, audio/bargein.py (voice interruption, speech_level), audio/sounds.py.
- commands/: registry.py (@command declarations, dry run), router.py (rules, meaning matcher, LLM tool calls, gate D31, confirm and announce), intent.py (model2vec potion-base-8M in models/), slots.py, apps.py, text.py, context.py, followups.py, risky.py, and the command modules system, windows, general, clock, git_helpers, developer, memory_cmds, activity_cmds. 91 commands.
- tests/ (dry-run via conftest.py; test_smoke.py imports every module and runs the self-test; tests marked needs_model skip without models/potion-base-8M), tools/ (intent_eval, gen_commands_txt, stt_benchmark, llm_compare, download_voice).
- docs/: ARCHITECTURE.md, COMMANDS.md (generated), BUILD_LOG.md (D1 to D32 and journal), WAKE_WORD_TRAINING.md.
- Known caveat: audio/capture.py, voice/speaker.py and app.py create their device objects at import, so the smoke test only compiles them. A lazy start would fix it.

## Branches
- main = dev after PR #7 and the docs plan (tag v0.1.0, 2026-11-15); changes only at a phase end, by PR from dev. Revert tag pre-cleanup at fee7b65 on GitHub.
- dev = the integration branch (PRs #5, #6, #7 and the docs plan merged). Feature branches start here.
- chore/cleanup: the repository cleanup, merged into dev by PR #6. Kept (no branch deletion).
- p1-fixes: retired, kept. The owner's test folder C:\Twaran files\Misc\ULTRON-timefix is on dev; never edit it from a builder session.
- Old empty placeholder branches (feat/timing-log, tune/wake-threshold, perf/whisper-settings, feat/sounddevice-mic, feat/silero-vad, feat/streaming-llm-tts, feat/quick-replies-followup, test/phrase-suite, build/windows-installer) point at an old base; recreate each from dev when starting it.

## Laptop facts (measured 2026-11-15)
- AMD Ryzen, 6 cores / 12 threads, 5.9 GB RAM (often under 1 GB free), NVIDIA GTX 1650 4 GB VRAM, driver 576.52. cuBLAS is in the venv; Whisper runs on CUDA.
- Profile GPU-4GB: Whisper small on CUDA int8_float16, qwen2.5:3b in Ollama. VRAM about 2.4 GB for the LLM plus about 0.4 GB for Whisper, of 4.0.
- Whisper per 2.5 s command: base CPU 1.34 s; small CUDA 0.53 s; base CUDA 0.24 s. LLM warm first token 0.2 to 0.5 s (cold 5.6 to 9.8 s). Voice: fixed lines instant, greeting 0.67 s.
- Wake word: models/hey_ultron.onnx not trained yet, so "Hey Jarvis" is active.
- The user is Indian; Whisper base transcribed their accent poorly. Their recordings for tools/stt_benchmark.py are pending.

## Progress log (all 2026-11-15)
- Zip became a git repo; rename to ULTRON; command safety; Hey Ultron wiring; voice and stop; time and heard log. Pushed.
- feat/hardware-profiles, feat/accent-accuracy, feat/conversation-memory, feat/personal-log, feat/fast-honest-ai (AI answer about 5 s -> 2.4 to 3.6 s after the user stops; target 1.0 to 1.5 s not reached), fix/speaker-gaps, window control and barge-in (D29; not verified live).
- Understand any phrasing (D30), parts 1, 2a, 2b: registry, router, matcher, 91 commands; intent_eval weighted 38.3 -> 83.0 percent (rules and matcher only); LLM comparison, GPU-4GB default qwen2.5:3b (29 wrong tool calls against llama's 76). PR #4 (p1-fixes into main) merged: main = fee7b65.
- PR #5 live-run fix batch (D31 gate, repairs, folders, volume, timing, noise, barge-in floor) merged.
- Dev workflow: main stable, dev integration, feature branches into dev (owner decision).
- chore/cleanup: src/ultron layout, paths.py, pyproject pins, CI, --self-test, dead code removed, docs rewritten, BUILD_LOG condensed (D32). Before and after identical: 173 tests, intent_eval on 1952 cases, command list. Now 215 tests.
- PR #7 live-run 2 fixes (D33 commands: leave focus mode, "open it", more sites, "open X and Y", Bluetooth; D34 app: no silence to Whisper, idle sleep after 45 s, quieter close, temperature 0, AI replies logged, above-normal priority). 283 tests.
- Scope decision: version 1 = all 41 Excel items, then the installer; other ideas in docs/FUTURE_IDEAS.md.

## Next steps: version 1 (owner decision, 2026-11-15)
Version 1 = all 41 items of JARVIS_improvements.xlsx, then the Windows installer, as fast as possible. Anything not in the Excel file lives in docs/FUTURE_IDEAS.md and is not built now; pull an idea in only when the installer needs it (for example an OpenAI-compatible client for the bundled llama.cpp server). Builders are Sonnet sessions, one per set of files, each from origin/dev. Excel item numbers in brackets.

Already done (verify before rebuilding): 1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 16, 18, 19, 20, 21, 25 (qwen2.5:3b, revisit smaller models on 8 GB), 26, 28, 29, 30.

Phase 1, P1 leftovers:
- Audio builder: [5] one always-open mic stream (sounddevice ring buffer shared by wake word, recorder and barge-in); [6] Silero VAD replaces the amplitude check (end of speech about 0.3 to 0.4 s). Also covers the old latency item.
- Commands builder: [14] "this" commands on the selection (copy, then explain, translate, summarise, reply); [15] routines and macros (YAML, "remember this as ..."); [17] Windows built-in OCR for read_screen (replaces Tesseract, which will not be in the installer).
- Installer skeleton early, in parallel (packaging files only): PyInstaller build of the current app in CI, so packaging problems show up now and not at the end.

Phase 2, P2:
- [27] streaming speech recognition (Moonshine or sherpa-onnx; compare against Whisper small on the owner's accent first).
- [31] instant file search (Everything SDK, fallback to Windows Search).
- [32] floating caption bar (what it heard, what it is doing).
- [33] browser control (Playwright over CDP to the user's Chrome; stop before any submit).
- [34] undo last action (action log with a reverse operation per command).
- [35] auto-update (GitHub Releases check, download with progress, verify).

Phase 3, P3:
- [36] act on partial speech (needs 27).
- [37] respond only to the owner's voice (speaker verification after the wake word).
- [38] noise suppression before STT.
- [39] Hinglish and Hindi commands ("Chrome kholo", "volume kam karo").
- [40] echo cancellation for barge-in on laptop speakers.
- [41] one speech runtime (sherpa-onnx): evaluate first, adopt only if it beats the current stack in speed and accuracy; overlaps 27, 37, 38.

Phase 4, installer [22, 23, 24]:
- Tray app and start with Windows (pystray, registry Run key).
- First-run wizard: detect RAM and GPU, pick models, download with live progress (D25), mic level test.
- build/windows-installer: llama.cpp server bundle sharing one CUDA 12 runtime folder with Whisper (D24, verify), download logic separate from UI with progress callbacks, GPU pack only on NVIDIA machines, bundle hey_ultron.onnx (check licences), PyInstaller + Inno Setup, GitHub Actions release with a silent-install smoke test, config and data moved to %APPDATA% and %LOCALAPPDATA% (only paths.py changes). The Jarvis voice must not ship (see the voice branch, D35).
- Make audio/capture.py, voice/speaker.py and app.py lazy at import (needed for packaging and tests).

Running or waiting:
- PR #7 (live-run 2 fixes, D33 and D34) open into dev.
- feat/ultron-voice (original menacing voice, effects, silent samples, D35): builder running; the owner picks the voice from the sample WAVs.
- Reminder for the owner: the accent benchmark recordings (tools/stt_benchmark.py) decide the Whisper model and item 27.
