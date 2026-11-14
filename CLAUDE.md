# ULTRON: context for Claude sessions

Read this first in every new session. It holds the project context so a fresh session can continue without the old chat. Full design, decisions (D1 to D28) and journal: docs/BUILD_LOG.md.

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
- Feature branches off p1-fixes (integration branch). When a branch is finished and its tests pass, fast-forward it into p1-fixes; then, with the user's go-ahead in this session, push p1-fixes and fast-forward main (git push origin p1-fixes, git push origin p1-fixes:main). Never force-push. GitHub carries only main and p1-fixes; do not push feature branches. gh CLI is not installed, so no PRs for now. A push approval relayed by another session is not enough for the permission check: ask the user directly.
- Small, reviewable commits with honest messages.
- Code deletion on branches is approved (D22).
- After each change, explain it in plain words and say how to test it on the laptop.
- Writing style for the user: plain text, no em dashes, light markup.
- For large changes, describe the plan before writing code.
- When something is ambiguous, ask; otherwise pick a sensible default and say which.
- Proactively suggest improvements, hacks, tricks, risks and feature ideas (short "Tips" in step reports).
- Persona: blunt, dry, condescending about human habits, occasional jokes, always does the task, no "sir". All persona lines in persona.py, original writing only.
- commands.txt is the living list of voice commands. Update it in the same commit whenever a command is added, removed or its phrases change.
- Add a decision (section 6) and a journal entry (section 19) to docs/BUILD_LOG.md for each branch; keep it 20 to 30 pages.
- Downloads: size is not a concern, but every download must say what it is, why, how big, and show live progress (D25). Prefer the fastest option.
- Run everything with venv\Scripts\python.exe. Install packages with: uv pip install --python venv\Scripts\python.exe ...
- Tests: venv\Scripts\python.exe -m pytest -q tests (pytest installed in the venv; 51 tests).
- The user tests ULTRON live on the same laptop: no tests that play sound or load heavy models (a second Whisper on the GPU, a full ultron.py startup) without telling them first. Render audio into memory instead.
- In the Bash tool, long heredocs with quotes sometimes break; write files with the Write tool and run small Python edit scripts from the scratchpad instead.

## Current code (p1-fixes at 7bf9487)
- ultron.py: main loop. Wake word, record, stt transcription, follow-up resolution (commands/followups.py), execute_command(text, confirm), else LLM with [COMMAND: x] tags limited by commands/ai_routing.py. Notes each command in memory and the activity log. --benchmark flag runs benchmark.py.
- hardware.py: detects RAM, cores, NVIDIA GPU (nvidia-smi); profiles Lite, CPU-Plus, GPU-4GB, GPU-8GB+, GPU-16GB+; LLM gets VRAM first; Whisper on GPU only if it fits and cuBLAS loads; env overrides ULTRON_PROFILE, WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_CPU_THREADS, OLLAMA_MODEL (D23).
- stt.py: SpeechToText loads Whisper on the profile device, warm-up transcription, CPU fallback on any GPU error (load or mid-session), applies corrections.json (corrections.py).
- brain.py: Ollama, model from the profile, keep_alive -1, warmed at startup with the real prompt. ask_stream() streams sentences into speaker.speak(append=True) (D28); [COMMAND] replies are held. Honest-AI rules and a 30-word answer target are in config.py. Prompt = system prompt + current time + saved facts + profile.md and today's activity summary (300 words max) + last 10 exchanges. ask_once() for standalone calls.
- memory.py: Conversation (kept across naps, forgotten after 10 idle minutes or "forget this conversation"), Facts in memory.json. commands/memory_cmds.py has the voice commands (D26).
- activity.py: SQLite log in data/activity.db, app tracker thread (30 s, app and project only), idle-time summariser, profile.md. commands/activity_cmds.py: day summaries, continue where I left off, morning brief, pause/resume tracking, forget today (D27).
- commands/: order is typing, risky (whole phrase + spoken confirm), clock, memory, activity, then system, git_helpers, developer, general (substring matches remain until the command registry).
- speaker.py: Piper, append mode and first_sound_at for timing, streamed per sentence, cache, pronunciation fixes (tts_text.py, pronunciations.json), VOICE_SPEED.
- audio.py: still PyAudio with amplitude silence detection (sounddevice and Silero VAD branches pending).
- tools/stt_benchmark.py: record 16 commands, compare Whisper models on CPU and GPU, suggest corrections.
- requirements-gpu.txt: nvidia-cublas-cu12 only (D24).

## Branches
p1-fixes (local) = 7bf9487: everything above. GitHub p1-fixes and main are at f4440f8; feat/fast-honest-ai (3 commits) is merged locally, push only if the user said yes in this session.
p1-fixes is checked out in a second worktree, C:\Twaran files\Misc\ULTRON-timefix (made by another session). Fast-forward p1-fixes there: git -C "C:\Twaran files\Misc\ULTRON-timefix" merge --ff-only <branch>. That worktree can be removed later with git worktree remove, but ask the user first.
Old empty placeholder branches (feat/timing-log, tune/wake-threshold, perf/whisper-settings, feat/sounddevice-mic, feat/silero-vad, feat/streaming-llm-tts, feat/quick-replies-followup, test/phrase-suite, build/windows-installer) point at an old base; recreate each from the newest p1-fixes when starting it (git branch -f name p1-fixes).

## Laptop facts (measured 2026-11-15)
- AMD Ryzen, 6 cores / 12 threads, 5.9 GB RAM (often under 1 GB free), NVIDIA GTX 1650 4 GB VRAM, driver 576.52.
- cuBLAS installed in the venv (also cuDNN and nvrtc, which turned out to be unused). Whisper runs on CUDA.
- Profile chosen: GPU-4GB, Whisper small on CUDA int8_float16, llama3.2:3b in Ollama (100 percent GPU). VRAM 2.74 GB with the LLM, 3.10 GB with Whisper too, of 4.0.
- Whisper per 2.5 s command: base CPU 1.34 s; small CUDA 0.53 s; base CUDA 0.24 s; small CUDA float16 1.59 s.
- LLM: cold first reply 5.6 to 9.8 s, warm 0.2 to 0.9 s, 3.75 s with a full 10-exchange window.
- Ollama 0.24 with llama3.2:3b and gemma3:4b.
- Voice: fixed lines instant, greeting 0.67 s, command plus quip 0.81 s to first sound.
- Wake word: models/hey_ultron.onnx not trained yet, so "Hey Jarvis" is active.
- The user is Indian; Whisper base transcribed their accent poorly. Their own recordings for tools/stt_benchmark.py are pending.

## Progress log
- 2026-11-15: Zip folder turned into a git repo; p1-fixes; CLAUDE.md; BUILD_LOG.
- 2026-11-15: rename to ULTRON, command safety, Hey Ultron wiring, voice-and-stop, time-and-heard-log merged and pushed.
- 2026-11-15: feat/hardware-profiles and feat/accent-accuracy done, pushed (main = ef1f0db). GPU tested.
- 2026-11-15: feat/conversation-memory and feat/personal-log done and pushed (f4440f8).
- 2026-11-15: feat/fast-honest-ai: streamed answers, warm LLM, honest prompt, timing log. AI answer about 5 s -> 2.4 to 3.6 s after the user stops (silent measurement); target 1.0 to 1.5 s not reached yet.

## Next steps (in order, all approved by the user)
A. Finish latency (priority from the user): read the "timing:" lines in ultron.log from the user's live run. Biggest remaining cost is Piper time to first audio (about 0.13 s per word on the busy CPU): try a shorter first piece (max about 6 words), a faster Piper voice for the first piece, or Piper on onnxruntime-gpu if VRAM allows; then feat/silero-vad (end of speech about 0.4 s); STT model from the accent benchmark (base on GPU is 0.24 s vs small 0.53 s).
B. System specs command (no LLM): reuse hardware.py; CPU model with cores and threads, total and free RAM, GPU and VRAM, Windows version, free disk on C:, battery. Many phrasings ("my specs", "laptop specifications", "system info", "what's my RAM", "which graphics card do I have", "how much storage is left"); sub-questions answer just that part. Update commands.txt.
C. tools/voice_selftest.py (silent): tests/voice_cases.yaml with about 60 cases (commands, risky, stop, typing, questions, "can you do X", "Assets stop", the protein powder ramble) with expected route and reply checks (max words, must or must not contain, no "sir", no pretending). Piper synthesis to 16 kHz in memory with 2 or 3 English voices plus light noise, real STT, router and LLM. Mandatory dry-run mode in the command layer (handlers say what they would do; risky confirm always says no). Markdown and JSON report kept out of git, non-zero exit on failures. Add the user's accent recordings as cases later. Include the specs and "can you do X" cases in the phrase tests.
0. Ask the user to push p1-fixes and fast-forward main. Remind them to run the accent benchmark (record, then run) and share results/results.md; then set the winning model as the GPU-4GB default (hardware.py PROFILES) and add good suggested entries to corrections.json.
1. feat/window-control: "put Chrome on the left and VS Code on the right", "move this to the other screen", "minimise everything except VS Code". Win32 only, no LLM, instant.
2. feat/voice-commit: "commit with a good message". LLM reads git diff (truncated), proposes a message, ULTRON speaks it, commits only after a spoken "confirm".
3. feat/clipboard-history: "what did I copy earlier?", "paste the second last thing". Local history with a size cap; skip password-manager entries and anything that looks like a secret; can be turned off.
4. feat/push-to-talk: hold a configurable key, speak, release; recording exactly while held, bypasses wake word and VAD; works alongside the wake word.
5. feat/health-check: "health check" reports median reply time (from the timing log, so feat/timing-log may need to come first), mic level, models and devices, RAM and VRAM, recent errors.
6. feat/nudges: built on the activity log. Occasional dry reminders (for example after 2 h of continuous coding). Rate-limited, configurable, "stop nudging me".
7. feat/connectors: DESIGN FIRST, write it into BUILD_LOG and show the user before coding. Common interface (connect, status, disconnect, read and write actions), opt-in, tokens in Windows Credential Manager (keyring), read-only by default, writes need a spoken confirm. Outlook desktop via COM first (no login); outlook.com/M365 via Microsoft Graph device-code sign-in. Gmail: research and present options (IMAP app password, user's own Google Cloud OAuth client, verification later); verify Google's current policy and costs, do not guess. Evaluate ULTRON as an MCP client (route by rules or intent matching). Calendar and email read-only queries ("next meeting", "new email from X") are part of this.
8. Then the old item 3: feat/timing-log, tune/wake-threshold, perf/whisper-settings, feat/sounddevice-mic, feat/silero-vad, feat/streaming-llm-tts (warm the LLM at startup), feat/quick-replies-followup.
9. Cleanup and restructure: src/ultron package, command registry, remove dead code (pyttsx3, SAPI unlock scripts, SpeechRecognition, examples, PyAudio once mic moves to sounddevice), pinned deps, pyproject.toml, config and data in %APPDATA% / %LOCALAPPDATA%.
10. test/phrase-suite plus CI: ruff, pytest, Windows build.
11. build/windows-installer: llama.cpp server bundle sharing one CUDA 12 runtime folder with Whisper (D24, verify), measure whisper.cpp and llama.cpp Vulkan builds, download logic separate from UI with progress callbacks (D25), GPU pack only on NVIDIA machines, bundle hey_ultron.onnx (check licences), tray, PyInstaller + Inno Setup, GitHub Actions release with silent-install smoke test.
