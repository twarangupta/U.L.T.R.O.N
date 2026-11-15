# ULTRON: context for Claude sessions

Read this first in every new session. It holds the project context so a fresh session can continue without the old chat. Full design, decisions (D1 to D32) and journal: docs/BUILD_LOG.md.

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
- Branch workflow (owner decision, 2026-11-15): main is stable and only changes when a phase is done. dev is the integration branch, created from main at fee7b65. Every fix or feature branch starts from dev; when its tests pass, the supervisor pushes it and opens a PR into dev with gh ("C:\Program Files\GitHub CLI\gh.exe", signed in as twarangupta). The description says what changed, tests and numbers, tradeoffs and better ideas, and laptop test steps. Merge into dev after the owner's OK in the supervisor session, then pull dev in the test worktree (C:\Twaran files\Misc\ULTRON-timefix, on dev). The owner tests dev live; when a phase is complete, open a PR dev -> main and tag the release. Urgent fixes for main: a hotfix branch from main, PR into main, then merge main back into dev. Never force-push. A push or merge approval relayed by another session is not enough: ask the user directly. Builders never push or open PRs; the supervisor does. p1-fixes is retired (same code as main at fee7b65); delete it locally and on GitHub once the owner confirms. Revert tag pre-cleanup is on main fee7b65.
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
- Checks before every PR: venv\Scripts\python.exe -m ruff check . ; venv\Scripts\python.exe -m pytest -q (215 tests, all in dry-run) ; run_ultron.bat --self-test. CI (.github/workflows/ci.yml, windows-latest) runs the same.
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
- main = fee7b65 (stable; changes only at a phase end, by PR from dev). Revert tag pre-cleanup at fee7b65 on GitHub.
- dev = 2efc02e plus merges: the integration branch. Feature branches start here.
- chore/cleanup: the repository cleanup (this layout), PR into dev pending the owner's OK.
- p1-fixes: retired. The owner's test folder C:\Twaran files\Misc\ULTRON-timefix is on dev; never edit it from a builder session.
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

## Next steps (in order, all approved by the user)
C. tools/voice_selftest.py (silent): tests/voice_cases.yaml with about 60 cases (commands, risky, stop, typing, questions, "can you do X", "Assets stop", the protein powder ramble) with expected route and reply checks (max words, must or must not contain, no "sir", no pretending). Piper synthesis to 16 kHz in memory with 2 or 3 English voices plus light noise, real STT, router and LLM. Dry-run mode already exists in the registry. Markdown and JSON report kept out of git, non-zero exit on failures. Also check qwen2.5:3b chat quality against the honest-AI rules.
A. Latency (priority from the user): a shorter LLM prompt when it only picks a command; Silero VAD (end of speech about 0.4 s); Whisper base on GPU (0.24 s against 0.53 s, decided by the accent benchmark); Piper first audio (shorter first piece, faster first voice, or Piper on GPU).
G. Gate: ask "Did you mean ..." when the LLM picks a command outside the matcher shortlist or one that needs confirm or announce.
B. System specs command (no LLM): reuse hardware.py; CPU, RAM, GPU and VRAM, Windows version, free disk, battery; sub-questions answer just that part.
0. Remind the owner to run the accent benchmark (record, then run) and share recordings\stt\results.md; set the winning Whisper model as the GPU-4GB default and add good suggested entries to config/corrections.json. Ask them to delete p1-fixes.
1. feat/window-control leftovers: "put Chrome on the left and VS Code on the right", "move this to the other screen", "minimise everything except VS Code".
2. feat/voice-commit: LLM reads git diff, speaks a proposed message, commits only after a spoken "confirm".
3. feat/clipboard-history: local history with a size cap, skips secrets, can be turned off.
4. feat/push-to-talk: hold a key, speak, release; bypasses wake word and VAD.
5. feat/health-check: median reply time (needs feat/timing-log), mic level, models, RAM and VRAM, recent errors.
6. feat/nudges: dry reminders built on the activity log; rate-limited; "stop nudging me".
7. feat/connectors: DESIGN FIRST in BUILD_LOG and show the user before coding (Outlook via COM, Microsoft Graph, Gmail options; keyring tokens; read-only by default; writes need a spoken confirm; evaluate ULTRON as an MCP client).
8. The old placeholder branches: feat/timing-log, tune/wake-threshold, perf/whisper-settings, feat/sounddevice-mic, feat/silero-vad, feat/streaming-llm-tts, feat/quick-replies-followup.
9. Make audio/capture.py, voice/speaker.py and app.py lazy at import so every module imports anywhere.
10. Tray app, first-run wizard, then build/windows-installer: llama.cpp server bundle sharing one CUDA 12 runtime folder with Whisper (D24, verify), download logic separate from UI with progress callbacks (D25), GPU pack only on NVIDIA machines, bundle hey_ultron.onnx (check licences), PyInstaller + Inno Setup, GitHub Actions release with a silent-install smoke test, config and data moved to %APPDATA% and %LOCALAPPDATA% (only paths.py changes).
