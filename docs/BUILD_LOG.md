# ULTRON Build Log

(Project renamed from JARVIS to ULTRON on 2026-11-15; see D21.)

A record of how ULTRON is built, from the first audit of the repo to the shipped installer: what we decided, why, what the stack and architecture are, and what happened at each step.

Owner: Twaran Gupta
Repo: https://github.com/twarangupta/U.L.T.R.O.N (renamed from J.A.R.V.I.S on 2026-11-15)
Started: 2026-11-15
Status: Phase 1 (fixes and speed) in progress

---

## Contents

1. About this log
2. Project summary and goals
3. Starting point: the repo as found
4. Problems found in the audit
5. Guiding principles
6. Decision record
7. Tech stack: now and target
8. Target architecture
9. Command system design
10. Safety model
11. Latency budget
12. Memory budget and hardware tiers
13. Testing strategy
14. Packaging and distribution
15. Branching and workflow
16. Roadmap
17. Limits and non-goals
18. Risks and open questions
19. Build journal
20. Appendix: config keys, glossary, test checklist

---

## 1. About this log

This document has two kinds of content.

Sections 2 to 18 are the design: goals, decisions, stack and architecture. They are kept current. When a decision changes, the old decision is marked "Superseded" with the date and the new one is added below it, so the reasoning is never lost.

Section 19 is the build journal: dated entries, one per meaningful step (a branch merged, a measurement taken, a decision changed). Entries are short: what was done, what was measured, what is next.

Target length is 20 to 30 pages. If it grows past that, older journal entries get condensed into a summary paragraph per phase.

All memory and speed numbers marked "est." are estimates for a typical mid-range Windows laptop, used to compare options. Measured numbers are marked "measured" with the machine they came from.

---

## 2. Project summary and goals

### 2.1 What ULTRON is

ULTRON is a free, local, privacy-first voice assistant for Windows. You say "Hey ULTRON", give a command, and it controls the computer: opens apps and folders, types for you, runs git and developer tasks, changes volume and media, reads the screen, answers questions. It runs fully offline by default. Nothing you say leaves the machine unless you turn on an optional online feature.

### 2.2 Who it is for

- Developers who want hands-free git, terminal and project control.
- Anyone who wants Infina-style hands-free typing and app switching without a subscription.
- People with ordinary 8 GB laptops. Stronger machines unlock bigger models, but the base experience must work on 8 GB.

### 2.3 Goals, in priority order

1. Feels instant. A built-in command (open an app, volume, type) should act within 0.5 to 1 s after you stop talking. An AI answer should start speaking within 1 to 2 s.
2. Safe. It must never do something destructive by accident (reboot, delete, empty recycle bin). Risky actions need a spoken confirmation.
3. Hands-free. Wake word, follow-up listening without repeating the wake word, voice confirmations, and interrupting it by voice.
4. One-click install. A normal user downloads ULTRONSetup.exe, clicks through, and it works. No Python, venv, Ollama, Tesseract or command line.
5. Low memory without getting slower. Save memory by choosing smaller models, never by unloading models between commands (that adds cold starts).
6. Free and open source.

### 2.4 Success measures

| Measure | Target |
|---|---|
| Stop talking to action, built-in command | 0.5 to 1.0 s (measured, P50) |
| Stop talking to first spoken word, AI answer | 1.0 to 2.0 s (measured, P50) |
| False wake-ups | under 1 per hour of normal room noise |
| Command phrase test suite | 100 percent pass before every release |
| Total RAM, lean default | about 2.2 GB (est.) |
| Install | one .exe, under 250 MB, plus a model download of 1 to 3 GB |
| Accidental destructive actions | zero |

### 2.5 Comparable product

Infina (infina.so) offers a voice layer with three main triggers: type, send it, open app. It feels fast because it uses a fixed command set and on-device transcription; its AI features use cloud providers, and hands-free typing is paid. ULTRON aims to match the instant feel for simple commands, stay fully local and free, and go further with file, developer, browser and multi-step tasks.

---

## 3. Starting point: the repo as found

Audit date: 2026-11-15. The local folder was a zip download of main (68 commits on GitHub). Working tree matched origin/main exactly. The remote "development" branch had nothing that main lacked.

### 3.1 File map

| File | Role |
|---|---|
| ultron.py | Main loop: startup greeting, wake word, record, transcribe, route, speak |
| wakeword.py | openWakeWord wrapper, built-in "hey_jarvis" model |
| audio.py | PyAudio mic handling, phrase recording with amplitude silence detection, keyboard interrupt helpers |
| brain.py | Ollama client, full conversation history |
| config.py | Settings from environment variables, LLM system prompt |
| speaker.py | Piper TTS with jarvis-high voice, PyAudio playback in a thread |
| startup_audio.py | Startup and sleep tones |
| logger.py | Logging setup |
| commands/__init__.py | Router: system, git, developer, general, in that order |
| commands/system.py | Apps, folders, web search, volume, media, shutdown, restart, lock, recycle bin, screenshots (536 lines) |
| commands/git_helpers.py | git status, pull, push, stash, commit, branches, log, conflicts (161 lines) |
| commands/developer.py | Ports, docker, project tools (340 lines) |
| commands/general.py | Typing, notes, timers, OCR, weather, news, calculator, jokes, drafting (444 lines) |
| download_jarvis_voice.py | Downloads the Piper voice model |
| unlock_voices.py, .ps1 | Unlocks extra Windows SAPI voices (legacy from pyttsx3) |
| git_organic_committer.py | Script that recreates a staged commit history with pre-written messages |
| examples/ | Small test scripts for mic, Whisper, Piper, Ollama |

### 3.2 Runtime flow as found

```
startup tone -> "Initializing" -> load wake word -> load Whisper -> greeting
loop:
  reset LLM history
  open mic stream
  read 80 ms chunks until wake score >= 0.2
  close mic stream
  speak "Systems online" (reopens mic to listen for interrupt, closes it)
  conversation loop:
    open mic, record until amplitude < 500 for 0.8 s, close mic
    Whisper base, beam 5, VAD filter
    if "go to sleep" in text: back to wake mode
    execute_command(text) through 4 modules
    else ask Ollama (non-streaming, full history)
         regex for "COMMAND: x" in reply, run it
    synthesize full reply with Piper, then play
```

### 3.3 Stack as found

- Wake word: openWakeWord "hey_jarvis", threshold 0.2.
- Speech to text: faster-whisper base, CPU, int8, beam_size 5, built-in VAD filter.
- Brain: Ollama, llama3.2:3b, non-streaming, full history, routing via "[COMMAND: name]" tags.
- Voice: Piper, jarvis-high.onnx, whole reply synthesized before playback.
- Audio I/O: PyAudio for both mic and speaker.
- OCR: pytesseract, needs Tesseract installed separately.
- Windows control: pycaw for volume, pyautogui for keys, pyperclip for typing, ctypes for recycle bin.
- Install: Python 3.10, venv, pip install with ">=" versions, separate Ollama install and model pull, separate Tesseract install, voice download script. Runs in a terminal window.

---

## 4. Problems found in the audit

### 4.1 Safety bugs (fix first)

1. Substring match for shutdown and restart. commands/system.py checks `"shutdown" in clean_text` and `"restart" in clean_text`. "Restart the dev server" or "type restart later" reboots the PC after 5 seconds. No confirmation.
2. Empty recycle bin runs with no confirmation, using the no-confirm flag.
3. Typing is checked last. "type ..." lives in general.py, which runs after system.py, so text you dictate that contains a system keyword is executed instead of typed.
4. Sleep phrase by substring. "go to sleep" anywhere in a sentence sends ULTRON to sleep, for example "remind me to go to sleep at 11".
5. LLM-routed commands. Any "COMMAND: x" text in the model's reply is executed through the same substring router, so a confused small model can trigger a system command.

### 4.2 Reliability bugs

6. Wake threshold 0.2 is low and causes false wake-ups. Start at 0.5 and tune with real data.
7. The mic stream is opened and closed between wake, record and speak modes. Each reopen costs time, loses audio at the start of speech, and can raise PortAudio errors.
8. End of speech by raw amplitude (max sample > 500) fails in noisy rooms (never ends) and with quiet speakers (cuts off).
9. Terminal QuickEdit mode on Windows freezes the process when the window is clicked.
10. Dependencies use ">=" so a fresh install can pull breaking versions.

### 4.3 Honesty issue

11. git_organic_committer.py rebuilds an incremental commit history with pre-written messages. This misrepresents how the project was built. Decision: remove it (needs the owner's go-ahead because it touches the public repo). See D17.

### 4.4 Where the delay comes from (est., mid-range CPU)

| Stage | Time now (est.) | Cause |
|---|---|---|
| End-of-speech wait | 0.8 s | fixed amplitude silence timer |
| Mic reopen | 0.05 to 0.2 s | stream closed between modes |
| Whisper base, beam 5 | 1 to 3 s | beam search, timestamps, runs after you stop |
| Rule match | under 10 ms | fine |
| LLM (when used) | 2 to 6 s | non-streaming, full history, 3B model |
| TTS before first sound | 0.3 to 2 s | whole reply synthesized first |
| Total, built-in command | about 2 to 4 s | |
| Total, AI answer | about 4 to 11 s | |

### 4.5 Memory now (est.)

LLM 2.6 GB, Whisper base 300 MB, Piper high 200 MB, wake word 80 MB, Tesseract 80 MB, Python and libraries 350 MB. Total about 3.6 GB.

---

## 5. Guiding principles

1. Rules before AI. Anything that can be matched by a rule, a fuzzy match or a tiny intent model never touches the LLM. That is what makes it fast and cheap.
2. Measure before optimizing. The per-stage timing log comes first so every later change can be shown to help.
3. Keep loaded what you use. Models load once at startup and stay warm. Memory is saved by picking smaller models.
4. Safe by default. Destructive actions need a whole-phrase match and a spoken confirmation. AI output never runs a risky command without confirmation.
5. Local by default. Online features (weather, news, optional stronger model) are opt-in and clearly labelled.
6. Design for 8 GB, unlock upward. The base build must be pleasant on an 8 GB laptop with no GPU.
7. Reliable control order: OS calls and shell first, then Playwright for the browser, then UI Automation, then app-specific hooks, and only last screenshots and vision.
8. Small honest commits on feature branches, each tested on the laptop before merging.

---

## 6. Decision record

Each decision lists context, the decision, alternatives considered, and consequences. Status is Accepted unless noted.

### D1. Fully local by default
Context: privacy is the main reason to choose ULTRON over cloud assistants.
Decision: all core features run offline. Online features are opt-in. A user-supplied stronger model (local or API key) can be added later as an option.
Alternatives: cloud LLM for quality (Groq, OpenAI). Rejected as a default: privacy, cost, needs accounts.
Consequences: quality is bounded by small local models, so the rules-first design (D10) matters more.

### D2. 8 GB laptops are the primary target
Context: most users do not have a GPU or 16 GB+ RAM.
Decision: the default configuration must fit comfortably in about 2.2 GB and feel fast on CPU. The first-run wizard picks bigger models when RAM or VRAM allows.
Consequences: default LLM is 2B-class; heavier features (vision, long research) are optional tiers.

### D3. Keep models warm, never unload between commands
Context: unloading saves memory but adds 2 to 10 s cold starts.
Decision: load wake word, VAD, STT, TTS and LLM at startup, send one dummy prompt to warm the LLM, keep everything resident.
Consequences: memory is controlled by model choice (D4), not by unloading.

### D4. Smaller default LLM
Context: llama3.2:3b uses about 2.6 GB and has a Meta community license.
Decision: default to Qwen3.5 2B or Gemma 4 E2B (both Apache-2.0, both support tool calling), quantized Q4. On 8 GB PCs, Qwen3.5 0.8B can serve as a router only. Final pick after a side-by-side test on routing accuracy and speed.
Alternatives: keep llama3.2 3B (bigger, license less clean); Phi-class models (weaker tool calling at this size).
Consequences: about 1 GB saved (est.); routing prompts must stay short and explicit.

### D5. Bundle llama.cpp server instead of requiring Ollama
Context: requiring a separate Ollama install breaks one-click install.
Decision: ship llama.cpp's llama-server binary inside the installer, started and supervised by ULTRON on a local port, using its OpenAI-compatible API with streaming and tool calling. Ollama stays supported as an optional backend for users who already have it.
Alternatives: llama-cpp-python (in-process, but heavier builds and harder to package per CPU/GPU); Ollama bundled (large, own service model).
Consequences: we pick the right llama.cpp build (CPU AVX2, CUDA, Vulkan) per machine in the wizard. Brain code talks to one OpenAI-style interface for both backends.

### D6. One always-open mic stream with sounddevice
Context: PyAudio stream reopen causes gaps and errors; PyAudio is also awkward to package.
Decision: replace PyAudio with sounddevice. One input stream opens at startup, its callback pushes 16 kHz mono frames into a ring buffer. Wake word, VAD and recording all read from that buffer. Output also moves to sounddevice.
Consequences: no lost audio at speech start (we can include 300 ms of pre-roll), no reopen delay, one less native dependency.

### D7. Silero VAD for end of speech
Context: amplitude thresholds fail with noise and quiet voices.
Decision: Silero VAD (ONNX, about 2 MB) on 32 ms frames. End of speech after about 0.4 s of non-speech, tunable. Max phrase length 10 to 15 s.
Consequences: about 0.4 s saved per command and fewer cut-offs. Runs on onnxruntime, which we already load.

### D8. Tune faster-whisper now, consider streaming STT later
Context: Whisper base with beam 5 takes 1 to 3 s after you stop talking.
Decision (now): beam_size=1, without_timestamps=True, condition_on_previous_text=False, language "en", our own VAD so Whisper's VAD filter can be turned off. Add hotwords / initial_prompt built from app names and commands.
Decision (P2): evaluate Moonshine or sherpa-onnx streaming models so text is ready as you stop talking.
Consequences: roughly 2x faster transcription (est.); accuracy checked with the phrase recordings.

### D9. Keep Piper, stream it
Context: the jarvis-high voice is part of the product's identity; latency comes from synthesizing the whole reply first.
Decision: keep Piper. Synthesize and play chunk by chunk. For LLM replies, split the token stream on sentence ends and queue each sentence to TTS. Cache 20 to 30 common replies ("On it, sir", "Opening Chrome", "Done") as WAV at first run and play them instantly.
Alternatives: Kokoro (good quality, larger); sherpa-onnx TTS (P3 option, same voice can run there).
Consequences: first sound within about 200 ms for cached replies and about 0.5 s for synthesized ones (est.). Piper medium voice is an option for low-RAM tiers.

### D10. Command registry with whole-phrase matching and priority
Context: four modules checked in a fixed order with substring tests cause most of the safety bugs.
Decision: one registry. Each command declares patterns (for example "open {app}"), a priority, a risk level and a handler, using a decorator. Matching uses word boundaries and anchored patterns. Dictation and typing commands have top priority. The router returns the best match with a score, not the first module that says yes.
Consequences: commands are easy to add and test; the old modules are migrated one by one.

### D11. Voice confirmation for risky actions
Context: shutdown, restart, log off, empty recycle bin, delete, force push and similar should never run by accident.
Decision: risk levels safe, confirm, blocked. "confirm" commands ask "Say confirm to restart the computer" and wait up to 6 s; only "confirm" or "yes confirm" proceeds. Anything else cancels. LLM-routed commands with risk "confirm" always confirm.
Consequences: one extra second for risky actions, zero accidental reboots.

### D12. Native tool calling instead of [COMMAND] tags (P2)
Context: regex over free text from a small model is fragile.
Decision: give the LLM a JSON schema per command (through llama.cpp or Ollama tool calling) and execute only valid tool calls through the registry, with the same risk checks.
Consequences: fewer broken AI-routed commands. Tags stay as a fallback until the switch is tested.

### D13. Windows built-in OCR instead of Tesseract
Context: Tesseract is an extra install and about 80 MB.
Decision: use Windows.Media.Ocr through winocr or winrt packages.
Consequences: no separate install, about 50 MB saved (est.), Windows 10/11 only (fine for a Windows-first app).

### D14. Windows installer: PyInstaller plus Inno Setup, built on GitHub Actions
Context: users should not install Python or anything else.
Decision: restructure into a proper package (pyproject.toml, pinned versions, src layout, config file in %APPDATA%). Bundle with PyInstaller in onedir mode (Nuitka as a fallback if size or startup time is poor). Wrap with Inno Setup into ULTRONSetup.exe. Build on a windows-latest GitHub Actions runner on every tag; publish to GitHub Releases.
Alternatives: MSIX (store-friendly but sandbox limits system control); Briefcase; Tauri now (bigger rewrite).
Consequences: installer about 150 to 250 MB; models are downloaded by the wizard, not bundled.

### D15. Tray app, first-run wizard, start with Windows
Decision: run without a console window, with a pystray tray icon (status, pause listening, settings, quit). First-run wizard detects RAM and GPU, recommends and downloads a model from Hugging Face with progress and checksum, tests the mic level and the wake word, and offers "start with Windows" through the user Run registry key.
Consequences: fixes the QuickEdit freeze; gives normal users a clear setup path.

### D16. Tauri desktop app later
Decision: after the installer is stable, build a Tauri 2 app (React and TypeScript UI) with the Python engine as a sidecar process. The engine exposes a small local API so the UI can be swapped without touching the engine. macOS after that; Linux best effort (Wayland limits global control).

### D17. Remove git_organic_committer.py
Decision: delete it in a dedicated commit with an honest message. Pending owner approval because it changes the public repo.
Update 2026-11-15: approved under D22; deleted on fix/command-safety.

### D18. Feature branches with an integration branch
Decision: p1-fixes is the integration branch for phase 1. Each feature gets its own branch from p1-fixes, is tested on the laptop, then merged back. main only receives tested phase merges through pull requests. See section 15.

### D19. Session handoff through CLAUDE.md
Context: long AI-assisted sessions lose quality as context fills.
Decision: CLAUDE.md at the repo root holds context, rules, progress and next steps. At about 30 to 40 percent context the session updates it, commits, and work continues in a fresh session.

### D20. Code signing
Context: unsigned installers trigger SmartScreen warnings.
Decision: apply to SignPath Foundation (free for qualifying open-source projects). Azure Trusted Signing is limited to individuals in the USA and Canada, so it does not apply. Fallback: an OV certificate (about USD 200 to 300 per year). Unsigned beta builds are acceptable early on with clear instructions.

### D21. Rename to ULTRON with an Ultron-style personality
Context: the owner chose a new name and character.
Decision: the assistant is ULTRON everywhere (code, prompts, docs, file names). Personality: blunt, calm, dry, a little condescending about humans, occasional short jokes about human habits, never cruel, always does the task, no "sir". All lines live in persona.py and are original writing, not quotes. A small random chance (ULTRON_QUIP_RATE, default 0.15) adds a remark after successful commands; never after errors or confirmations. Wake replies are one or two words to keep latency low.
Wake word: openWakeWord ships only "hey_jarvis", so it stays the wake phrase until a custom "hey ultron" model is trained (or sherpa-onnx open-vocabulary keywords are adopted). Decision pending with the owner.
Update 2026-11-15 (decided): train a custom "Hey Ultron" openWakeWord model with the project's Colab notebook (sherpa-onnx keywords not adopted). The owner trains it (docs/WAKE_WORD_TRAINING.md) and saves it as models/hey_ultron.onnx; ULTRON uses it when present and falls back to hey_jarvis with a log warning otherwise. WAKE_WORD_MODEL still overrides. The installer phase must bundle the trained model (check training-data licences first).
Voice: the Piper voice is unchanged (it is a JARVIS-style voice); saved locally as ultron-voice.onnx, with a fallback to the old file name.
Note: Ultron and JARVIS are Marvel characters. Fine for a personal open-source project; if the product is distributed widely or monetized, an original name and voice avoid trademark and voice-likeness problems.

### D22. Full cleanup and installer mandate
Context: the owner asked for neatly organized, human-readable code with less unnecessary code, plenty of CI, and a fully functional, tested installer at the end.
Decision: after phase 1 behavior fixes, restructure into src/ultron with a command registry, delete dead and legacy code (pyttsx3 path, SAPI voice unlock scripts, SpeechRecognition, duplicate examples, git_organic_committer.py), pin dependencies, add CI (lint with ruff, tests with pytest, Windows build of the installer, silent-install smoke test), and ship UltronSetup.exe renamed UltronSetup.exe.

### D23. Hardware profiles pick the models
Context: one fixed setup either holds strong PCs back or overloads weak ones. The owner's laptop (GTX 1650 4 GB, 5.9 GB RAM) also needs the GPU shared carefully.
Decision: hardware.py detects RAM, cores and the NVIDIA GPU (nvidia-smi) once at startup and picks a profile: Lite, CPU-Plus (no GPU but 16 GB+ and 8+ cores, added so strong CPU-only PCs are not held back), GPU-4GB, GPU-8GB+, GPU-16GB+. The LLM gets VRAM first (Ollama file size plus 0.8 GB); Whisper goes on the GPU only if the rest, minus a 0.5 GB reserve, still fits. Whisper uses the GPU only when the CUDA libraries load, and stt.py falls back to the CPU on any GPU error at load or mid-session. The LLM is the best installed model from the profile's list, with an "ollama pull" hint when the best one is missing. Every choice is overridable (ULTRON_PROFILE, WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_CPU_THREADS, OLLAMA_MODEL). ultron.py --benchmark prints the profile and timings.
Consequences: Ollama still decides its own GPU layers and threads; we only choose the model.

### D24. GPU pack is cuBLAS only
Context: faster-whisper on CUDA needs NVIDIA runtime DLLs that a plain venv does not have.
Decision: ship only nvidia-cublas-cu12 (cublas64_12.dll and cublasLt64_12.dll, 772 MB on disk, about 550 MB download). Measured on the GTX 1650: ctranslate2 4.9 loads exactly these two plus its own DLLs and never touches cuDNN; Whisper transcribes correctly with cuDNN removed from the DLL path. The full cuBLAS + cuDNN + nvrtc set was 2.0 GB.
Shared runtime (plan, verify in the installer phase): llama.cpp's CUDA 12 Windows build needs cudart64_12, cublas64_12 and cublasLt64_12. ctranslate2 links cudart statically, so one folder with the two cuBLAS DLLs plus cudart (under 1 MB) can serve both, as long as both are CUDA 12 builds (cuBLAS is backward compatible within 12.x).
Not measured yet: whisper.cpp and llama.cpp Vulkan builds (would cover AMD and Intel GPUs without the CUDA pack). Needs downloading their binaries; do it in the installer phase and record size and speed here.

### D25. Every download says what it is and shows progress
Context: download size does not worry the owner, silence does. The installer gets a custom UI later.
Decision: prefer the fastest option over the smallest. Every download (LLM, Whisper models, GPU pack, voice, wake word) states what it is, why it is needed and its size, and reports live progress: percent, MB done of total, and speed or time left. Download and setup logic lives in a UI-free module that reports progress through callbacks, so the console, the first-run wizard and the future installer UI can all drive it. The base installer has no NVIDIA libraries; the wizard downloads the GPU pack only on NVIDIA machines.

### D26. Conversation memory and long-term facts
Context: the history was wiped every time ULTRON went to sleep, so "close it" after a nap meant nothing.
Decision: memory.py keeps the conversation across naps and forgets it after 10 minutes of silence (CONVERSATION_FORGET_MINUTES) or on "forget this conversation". Each command ULTRON runs is added as an exchange ("open chrome" -> "(ran a command) Opening Chrome."). Only the last 10 exchanges (CONVERSATION_MAX_EXCHANGES) go to the LLM. Short follow-ups ("close it", "louder", "again") are resolved by rules from the last command, not by the LLM (commands/followups.py); risky commands are never repeated. Long-term facts ("remember that ...") live in memory.json (readable, git-ignored) and are added to every system prompt (last 30).
Consequences: prompts grow with the window; measured 0.9 s warm reply with a short history and 3.75 s with a full 10-exchange window on llama3.2:3b. If that hurts, lower the window or summarise older exchanges.

### D27. Personal activity log
Context: the owner wants ULTRON to know what they worked on, to answer "what did I do yesterday" and "continue where I left off", without a cloud service or a heavy tracker.
Decision: activity.py. (1) Every command ULTRON runs is one row in a local SQLite file, data/activity.db (WAL mode): what was said, the result, the app, and for git commands the repo and branch read from .git/HEAD (no subprocess). (2) An app tracker thread, on by default (ACTIVITY_TRACKING=0 disables it, "pause tracking" pauses it): every 30 s one Win32 call reads the foreground window; time is added to (day, app, project) rows. The project name comes from editor titles (VS Code, Cursor, JetBrains). Titles are read in memory only, stored only if ACTIVITY_STORE_TITLES=1. Time is not counted after 5 min without input. An exclude list in data/activity_settings.json (password managers, InPrivate and Incognito windows, banking words by default) is never recorded. (3) A summariser thread asks the LLM for a 4-sentence day summary only when ULTRON has been unused for 20 min, never while a conversation is open (ACTIVITY_SUMMARIES=0 turns it off). The LLM sees a digest of app minutes and command phrases, never titles. (4) Every LLM prompt gets profile.md (user-written) plus today's summary, capped at 300 words. (5) Voice: day summaries, "continue where I left off" (last VS Code folder from VS Code's own storage.json, plus its branch), morning brief (yesterday, where you stopped, uncommitted changes), pause and resume tracking, forget today, tracking status.
Defaults chosen: tracker on (the owner asked for it), titles off. Everything stays in readable local files, git-ignored.
Measured cost (laptop): command write 0.065 ms median (0.74 ms max), tracker tick 0.07 ms (0.0002 percent of one core at one per 30 s), 3.6 MB RAM, about 84 KB of disk for a heavy day (500 commands), about 30 MB per year. Summary: one 4 s LLM call per idle period.

### D28. Streamed, warm and honest AI answers
Context: the owner measured more than 2 s (about 5 s in the log) from the end of a question to the first spoken word, and the model pretended it could read the laptop's specs.
Decision: stream the LLM reply and hand each finished sentence to the speaker queue (append mode); the first piece may end at a comma once it has 4 words, because Piper needs time per word before the first sound. Replies that start with a [COMMAND: x] tag are held and handled as before. keep_alive -1 keeps the model loaded (D3); it is warmed at startup with the real system prompt so the prompt is already processed, and re-warmed after idle summaries (which use a different prompt). num_predict is capped at 120 and the prompt asks for one or two sentences under 30 words. Honesty rules: general knowledge is answered; anything about this PC, private data, accounts or live information gets one short line saying it has no access, never pretending, inventing, offering to search or saying to check a connection. End-of-speech wait lowered from 0.8 to 0.6 s (END_SILENCE_SECONDS) until Silero VAD replaces it. One "timing:" log line per request (end_wait, stt, llm_first_token, first_sound, after_you_stopped).

---

### D29. Window control, voice barge-in, keyword-gated AI commands
Context: the owner reported that close and minimise did not work and that talking over ULTRON did not stop it; the log showed "close Google Chrome", "close VS code" and "minimize everything" all fell through to the LLM, and "I meant whey protein" (heard as "wave protein") triggered git log.
Decision: commands/windows.py handles close, minimise (all, all except X, one app, this), restore, maximise and switch with Win32 calls and an alias table; it never closes ULTRON's own process tree or the desktop (Progman, which opens the shut-down dialog), and only claims a sentence when it names a known or open app. bargein.py stops speech when the mic gets several times louder than the running echo level for about 0.3 s, and hands the captured audio to the next recording. Every AI-routed command now needs one of its key words in the user's sentence.
Consequences: no LLM for window control; barge-in on laptop speakers depends on the echo level (tunable, logged per reply); real echo cancellation stays a P3 item.

### D30. Understand any phrasing: one registry, three stages
Context: the owner does not want to fix phrasings one at a time ("even if the question went to ai, it should understand what command to execute"). Commands were matched by substring tests in five modules, and the LLM could only emit [COMMAND: x] tags for 15 commands behind hand-kept keyword lists (commands/ai_routing.py). Replaces D10's pattern-only registry and finishes D12.
Decision, registry: commands/registry.py. Each command is declared once with a decorator next to its handler:
```python
@command("volume_set", "Set the speaker volume to a percentage.",
         params=[Param("level", "int", "volume from 0 to 100")],
         examples=["set the volume to 40", "volume 70 percent", ...],   # 5 to 10
         not_examples=["what is the volume of a sphere"],              # near misses
         rules=[r"(?:set )?(?:the )?volume (?:to )?(?P<level>\d+)(?: percent)?"],
         risk="safe")                                                  # safe, confirm or blocked
def volume_set(level: int) -> str: ...
```
Optional fields: announce=True (medium impact: say what is about to happen first, so barge-in can stop it), confirm_text ("restart the computer"), stages (which stages may pick it; typing is rules only), priority. Parameter types: str, int, app, site, folder, day, enum. The handler returns the reply to speak ("" for silent). A registry-wide dry-run flag makes every handler return "Would run x(args)" instead of acting (intent tests, the voice self-test).
Decision, three stages, fastest first (commands/router.py), after the stop and sleep phrases and dictation, which keep top priority:
- a. Rules: the declared regexes, matched against the whole normalized sentence (fullmatch) after polite request words are stripped ("can you", "could you please", "I want you to"). Named groups fill the parameters. Instant.
- b. Meaning matcher (intent.py): model2vec potion-base-8M (MIT, 30 MB, loads in 0.5 s, 0.1 ms per sentence on the laptop) embeds the sentence and compares it with every example. Score = best cosine per command. A small "not a command" set (questions, chat, near misses such as "restart the dev server") and each command's not_examples act as a null class: if the sentence is closer to them, there is no match. Starting thresholds (tuned on tests/intents.yaml and updated below): run at 0.80 or more with a margin of 0.05 over the null class; 0.62 to 0.80 asks "Did you mean ...?"; below 0.62 goes to stage c. Parameters come from slot fillers: numbers (digits and number words), app names (alias table plus fuzzy match with rapidfuzz, score 80 or more), sites, folders, branch names and free text after a cue word. A match whose required parameter cannot be filled goes to stage c.
- c. LLM with native tool calling (Ollama tools API). To keep the prompt short on a 4 GB GPU, only the top 6 commands from the matcher whose score is at least 0.35 are offered as tools; with none, the model just answers. A tool call is checked against the schema (known name, required arguments, types, enums) and must be one of the offered tools; then it runs through the same registry path as a match. Text replies stream to the voice as before, honest-AI rules unchanged. [COMMAND] tags, their prompt section and ai_routing.py are removed.
Each stage is timed; the timing line gains route=rule|match|tool|llm, cmd=<name> and rule_ms, match_ms. Stages a and b must stay well under 50 ms.
Decision, safety (structural, the same for every stage): risk confirm always asks for the spoken confirm (D11), whichever stage picked it, and skips "Did you mean" because the confirm prompt already names the action. Risk blocked never runs; ULTRON says it will not. announce commands (close an app, git push, git commit, kill a port, organize downloads) say the action first ("Closing Chrome."); if the user talks over it, it is cancelled. A low-confidence match asks "Did you mean X?"; only yes (yes, yeah, yep, correct, do it, sure) runs it, anything else cancels. Short fragments under 3 words never reach the matcher's run zone without a rule. Negative cases that must never trigger a command are in tests/intents.yaml.
Decision, tests: tests/intents.yaml holds 20 to 30 paraphrases per command (written at development time by the coding model, reviewed against each handler, and never copied from the registry examples), the owner's real "Heard" lines from ultron.log, and a negatives list. tests/test_intents.py runs stages a and b in pytest with dry-run handlers (no audio, no LLM); it skips when the 30 MB model file is missing. tools/intent_eval.py reports accuracy per stage, including the LLM stage against any Ollama model, and the old router on the same set. tests/test_commands_txt.py fails when commands.txt is not what tools/gen_commands_txt.py would write.
Update (supervisor review): model2vec vectors are static, so they ignore negation and word order ("don't close chrome" looks like "close chrome"). Guards in router.py: a negation (don't, do not, never, not) or a deferring time word (later, tomorrow, after lunch, in 5 minutes, at 11) outside the captured parameters means no command runs directly and the LLM gets no tools (timers and reminders keep their time words; dictation and "remember that I do not ..." are unaffected). A match also asks "Did you mean" unless it beats the second-best command by 0.03 (SECOND_MARGIN). The eval in part 2 weights the owner's real Heard lines above generated paraphrases, because paraphrases written by a model share its bias.
Tradeoffs:
- Speed: rules under 0.3 ms, matcher about 1.3 ms; startup gains about 1.5 s (model load plus index), done in a background thread. Tool stage: a shortlist of at most 6 schemas keeps the prompt short; the full list (89 schemas, several thousand tokens) would slow the first token on the GTX 1650 and may overflow the 4096-token context. Shortlist versus full list is to be measured in part 2.
- Memory: about 40 MB RAM for the matcher, no VRAM.
- Accuracy: the shortlist can miss the right command when the matcher ranks it below 6th; then the LLM answers in words instead of acting (safe failure). Guards are word lists, so "close chrome when the download ends" is caught but unusual deferrals may not be.
- Risk: lower than before, since every stage goes through one safety path; the remaining risk is a wrong but safe command run on a 0.80+ match, which the paraphrase eval measures.
- Complexity: five small modules replace five substring modules; each command is one declaration.
- Better ideas considered: an explicit "no tool" pseudo-tool (clearer for the model, but a call to it costs a second LLM round trip; measure in part 2); a cross-encoder or small classifier fine-tuned on the paraphrases (more accurate on negation, about 100 MB and 10 to 30 ms, worth it only if the eval shows the guards are not enough).
Consequences: a new command is one decorated function with examples; no code change for new phrasings of existing commands. The tool stage costs one LLM call only for sentences the matcher cannot place. Non-Windows branches in the old handlers are dropped (Windows-first, D22).

## 7. Tech stack: now and target

| Layer | Now | Target (P1 to P2) | Why | License |
|---|---|---|---|---|
| Language | Python 3.10 | Python 3.11 or 3.12 | faster, still well supported by deps | PSF |
| Audio I/O | PyAudio | sounddevice | one stream, easier packaging | MIT |
| Wake word | openWakeWord, 0.2 | openWakeWord, 0.5 plus tuning | works, small | Apache-2.0 |
| VAD | amplitude > 500 | Silero VAD (ONNX) | accurate, tiny | MIT |
| Speech to text | faster-whisper base, beam 5 | faster-whisper base, beam 1, hotwords; P2 Moonshine or sherpa-onnx streaming | speed | MIT |
| Matching | substring checks | registry, regex, rapidfuzz, correction dictionary; P2 model2vec | accuracy, safety | MIT |
| LLM runtime | Ollama | bundled llama.cpp server (Ollama optional) | one-click install | MIT |
| LLM model | llama3.2 3B | Qwen3.5 2B or Gemma 4 E2B, Q4 | memory, license | Apache-2.0 |
| LLM routing | [COMMAND] regex | P2 native tool calling | reliability | |
| Text to speech | Piper high, full synthesis | Piper, streamed, cached replies | latency | MIT |
| OCR | Tesseract | Windows.Media.Ocr | no install | Windows API |
| Windows control | pycaw, pyautogui, pyperclip, ctypes | same plus pywin32, UI Automation later | | MIT/BSD |
| App launching | hardcoded list | Start Menu .lnk and AppUserModelID index | open any app | |
| File search | none | P2 Everything (voidtools) via SDK, Windows Search fallback | instant | |
| Browser | webbrowser module | P2 Playwright over CDP to the user's Chrome | read and fill pages | Apache-2.0 |
| UI | terminal | tray (pystray), caption bar; later Tauri 2 | normal users | |
| Config | env vars, hardcoded paths | TOML file in %APPDATA%\ULTRON, env overrides | packaging | |
| Packaging | none | PyInstaller onedir plus Inno Setup | one .exe | |
| CI | none | GitHub Actions windows-latest | builds .exe | |
| Tests | none | pytest phrase suite, unit tests | regressions | |

---

## 8. Target architecture

### 8.1 Process model

Phase 1 and 2: one Python process (the engine) plus one child process (llama-server). Phase 3 with Tauri: the UI process talks to the engine over a local socket.

```
+---------------------------- ULTRON engine (Python) ----------------------------+
|                                                                                |
|  Mic (sounddevice callback) --> RingBuffer (30 s, 16 kHz int16)                |
|                                     |                                          |
|        +----------------------------+-------------------+                      |
|        v                            v                   v                      |
|   WakeWord (oww)              VAD (Silero)         Recorder (pre-roll)         |
|        |                            |                   |                      |
|        +-------------> Orchestrator (state machine) <---+                      |
|                               |          ^                                     |
|                               v          |                                     |
|                         STT (whisper)    |  events                            |
|                               |          |                                     |
|                               v          |                                     |
|           Normalizer -> Router (registry, fuzzy, intent) --> Handlers --> OS   |
|                               | no match                                       |
|                               v                                                |
|                       Brain (HTTP, streaming) ---------> llama-server (child)  |
|                               | sentences                                      |
|                               v                                                |
|                  Speaker queue -> Piper -> sounddevice out                     |
|                                                                                |
|  Timing log, config, app index, tray, logger                                   |
+--------------------------------------------------------------------------------+
```

### 8.2 Threads

- Audio callback thread (sounddevice): only copies frames into the ring buffer. Never blocks.
- Listener thread: reads the ring buffer in 80 ms steps, runs the wake word and VAD, emits events (WAKE, SPEECH_START, SPEECH_END).
- Main orchestrator thread: runs the state machine, calls STT, router and handlers.
- Brain thread: streams tokens from llama-server and pushes complete sentences to the speaker queue.
- Speaker thread: pulls sentences, synthesizes with Piper chunk by chunk, writes to the output stream; can be stopped instantly.
- Tray thread: pystray icon and menu.

### 8.3 State machine

```
SLEEPING --wake--> LISTENING --speech end--> THINKING --> ACTING/SPEAKING
    ^                  ^   |timeout                          |
    |                  |   v                                 v
    |                  +--FOLLOW_UP (6-8 s, no wake word) <--+
    |                          |timeout
    +--------------------------+
CONFIRMING: entered from THINKING for risky commands; "confirm" -> ACTING, else -> FOLLOW_UP
Any state: wake word or "stop" while SPEAKING -> stop speech -> LISTENING (barge-in)
```

### 8.4 Audio pipeline details

- Sample rate 16 kHz mono int16 for all input models.
- Ring buffer of about 30 s lets the recorder include 300 ms before speech start, so the first word is never clipped.
- Wake word uses 80 ms frames (1280 samples); Silero uses 512-sample frames (32 ms); the listener feeds each from the same buffer.
- During SPEAKING the wake word keeps running for barge-in. On laptop speakers this needs echo cancellation (P3); until then barge-in is reliable with headphones and keyboard interrupt remains.

### 8.5 Module layout (target)

```
src/jarvis/
  __main__.py          entry point, tray or console mode
  app.py               orchestrator and state machine
  config.py            load TOML + env overrides, paths in %APPDATA%
  timing.py            per-stage timer and log
  audio/
    stream.py          sounddevice input, ring buffer, output
    vad.py             Silero wrapper
    wakeword.py        openWakeWord wrapper
  stt/whisper.py       faster-whisper wrapper, hotwords
  tts/piper.py         streaming Piper, reply cache
  brain/
    client.py          OpenAI-style streaming client (llama-server or Ollama)
    server.py          start and supervise llama-server
    prompts.py
  commands/
    registry.py        @command decorator, matching, risk levels
    normalize.py       lowercase, punctuation, correction dictionary
    system.py git.py developer.py general.py typing.py apps.py
  platform/windows.py  volume, OCR, app index, foreground window
  ui/tray.py, ui/wizard.py
tests/
  phrases.yaml         phrase -> expected command pairs
  test_router.py
packaging/
  jarvis.spec          PyInstaller
  installer.iss        Inno Setup
.github/workflows/build.yml
```

Restructuring into src/ happens in the packaging phase, after the P1 behavior fixes, so each fix stays a small diff against today's files.

### 8.6 Data and config locations

- Program files: C:\Program Files\ULTRON (read-only)
- Config: %APPDATA%\ULTRON\config.toml
- Models: %LOCALAPPDATA%\ULTRON\models (large, not roamed)
- Logs and timing: %LOCALAPPDATA%\ULTRON\logs
- User data (notes, routines, corrections): %APPDATA%\ULTRON\data

---

## 9. Command system design

### 9.1 Matching pipeline

```
raw transcript
  -> normalize (lowercase, strip punctuation and fillers: "please", "jarvis", "can you")
  -> correction dictionary ("get push" -> "git push", "v s code" -> "vs code")
  -> dictation check (type / write / new line / send it / delete that)   priority 100
  -> exact and pattern match against registry (anchored, word boundary)  priority by command
  -> fuzzy match (rapidfuzz, score >= 88) on command phrases and app names
  -> P2: intent match (model2vec nearest example, similarity >= threshold)
  -> LLM fallback (answer, or tool call validated against the registry)
```

The first stage that produces a confident match wins. Ties go to higher priority, then to the longer pattern.

### 9.2 Registry example

```python
@command("restart (my|the) (computer|pc|laptop)", risk="confirm", priority=50)
def restart_pc(ctx): ...

@command("open {app}", priority=40)
def open_app(ctx, app): ...

@command("type {text}", priority=100, raw=True)
def type_text(ctx, text): ...
```

Patterns compile to anchored regular expressions. Slots like {app} capture text, and the app slot is resolved through the Start Menu index with fuzzy matching.

### 9.3 Risk levels

| Level | Examples | Behavior |
|---|---|---|
| safe | open app, volume, type, git status | run immediately |
| confirm | shutdown, restart, sign out, empty recycle bin, delete files, git push --force, kill process | spoken confirmation |
| blocked | format drive, registry edits, installs | refuse with explanation |

### 9.4 Command inventory (as found, about 40+)

Apps and folders, web search, volume and mute, media keys, lock, shutdown, restart, recycle bin, screenshots, git (status, pull, push, stash, pop, commit, branch, switch, log, conflicts), ports, docker, project tools, notes, timers, OCR, weather, news, calculator, jokes, typing, drafting. Each is migrated into the registry with at least three test phrases and one negative phrase.

---

## 10. Safety model

1. Whole-phrase matching for every system command. No substring tests anywhere in the router.
2. Dictation first. Text after "type" is never interpreted as a command.
3. Spoken confirmation for "confirm" risk commands, with a 6 s timeout that defaults to cancel.
4. AI output is never trusted to run risky commands. Tool calls go through the registry, which applies the same risk level.
5. Undo log (P2) for file moves, renames and organizing, with a reverse operation per action.
6. Browser automation (P2) stops before any submit, purchase or send, and asks.
7. No autonomous purchases, emails or installs.
8. Online calls (weather, news) are opt-in and listed in settings.
9. The phrase test suite includes negative cases ("restart the dev server" must not match restart_pc) and runs in CI.

---

## 11. Latency budget

Target for a built-in command, from the moment you stop talking:

| Stage | Budget | How |
|---|---|---|
| End-of-speech detection | 0.30 to 0.40 s | Silero VAD, 0.4 s silence |
| STT | 0.25 to 0.50 s | beam 1, no timestamps, warm model |
| Normalize and match | under 0.02 s | rules first |
| Action | 0.05 to 0.20 s | OS call |
| Spoken feedback start | under 0.05 s | cached WAV |
| Total | 0.6 to 1.1 s | |

Target for an AI answer: end of speech 0.4 s, STT 0.4 s, first sentence from a warm 2B model 0.3 to 0.8 s, Piper first chunk 0.2 s. Total 1.3 to 1.8 s to first word.

Every stage is measured by timing.py and written as one line per command, for example:

```
wake=0 rec=2.31 vad_end=0.38 stt=0.41 match=0.004 act=0.12 speak_start=0.03 total=0.94 route=rule cmd=open_app
```

The budget is reviewed after each P1 branch is merged, using the median of 20 test commands.

---

## 12. Memory budget and hardware tiers

### 12.1 Lean default (est.)

| Component | Now | Lean choice | RAM now | RAM lean |
|---|---|---|---|---|
| LLM | llama3.2 3B | Qwen3.5 2B / Gemma 4 E2B Q4, kept loaded | 2600 MB | 1600 MB |
| STT | Whisper base int8 | Whisper base now; Moonshine streaming later | 300 MB | 120 MB |
| TTS | Piper high | Piper medium (or keep high) | 200 MB | 120 MB |
| Wake word | openWakeWord | keep | 80 MB | 80 MB |
| VAD | amplitude | Silero | 0 | 10 MB |
| Intent matcher | none | model2vec potion-base-8M | 0 | 40 MB |
| OCR | Tesseract | Windows OCR | 80 MB | 30 MB |
| Python and libs | full set | trimmed, sounddevice | 350 MB | 250 MB |
| Total | | | 3610 MB | 2250 MB |

### 12.2 Tiers chosen by the wizard

| Tier | Hardware | Models |
|---|---|---|
| Lite | 8 GB RAM, no GPU | 2B-class LLM (or 0.8B router plus rules), Whisper base or Moonshine, Piper medium |
| Standard | 16 GB RAM or 6 to 8 GB VRAM | 4B to 9B LLM, Whisper small, Piper high |
| Power | 24 GB VRAM GPU with 64 GB RAM, or 64 GB+ Apple Silicon | 27B dense or 35B MoE class models, vision features, longer context |

An agent loop needs about 30 tokens per second to feel responsive. Long context slows first-token time a lot, so prompts stay short and the system prompt is cached by the server.

---

## 13. Testing strategy

1. Phrase suite. tests/phrases.yaml holds hundreds of "phrase -> command and slots" pairs, including negatives and dictation cases. pytest runs the router without audio. Runs in CI on every push.
2. Unit tests for normalize, correction dictionary, risk checks, config loading, sentence splitting for TTS.
3. Audio fixtures. A small set of recorded WAV files (wake word, short commands, noise) replays through VAD and STT to catch regressions in accuracy and timing.
4. Manual laptop checklist per branch (appendix 20.3): the exact steps to try, and what "pass" looks like.
5. Timing comparison. Each speed branch records before and after medians in the journal.
6. Installer smoke test in CI: install silently on the runner, launch with a "--self-test" flag that loads every model and exits 0.

---

## 14. Packaging and distribution

Yes, ULTRON ships as a Windows installer. This is the main delivery format for phase 1 and 2.

### 14.1 What the user gets

- ULTRONSetup.exe from GitHub Releases, about 150 to 250 MB.
- A normal install wizard (license, install folder, desktop shortcut, start with Windows).
- On first launch, the setup wizard: detects RAM and GPU, recommends a tier, downloads the model (1 to 3 GB) with progress, tests the mic and the wake word, and saves config.
- A tray icon. No terminal window.
- Uninstall from Windows Settings, with an option to keep or remove downloaded models.

### 14.2 What is inside the installer

- Python runtime and all libraries (PyInstaller onedir).
- openWakeWord model, Silero VAD, Whisper base, Piper voice (small enough to bundle).
- llama.cpp server binaries (CPU build always; CUDA or Vulkan build downloaded by the wizard if a GPU is found).
- Not inside: the LLM model weights (downloaded on first run so the installer stays small and the model matches the machine).

### 14.3 Build pipeline

```
git tag v0.x.y
  -> GitHub Actions (windows-latest)
     -> set up Python, install pinned deps
     -> run pytest
     -> PyInstaller (packaging/jarvis.spec)
     -> download bundled small models, verify checksums
     -> Inno Setup (packaging/installer.iss) -> ULTRONSetup.exe
     -> sign (when certificate is available)
     -> silent install smoke test
     -> upload to GitHub Release
```

Development happens on Linux-capable tools but the .exe can only be built on Windows, which is why the runner does it.

### 14.4 Updates

The app checks GitHub Releases at startup (opt-in), shows "update available" in the tray, and downloads the new installer, which upgrades in place and keeps config and models.

### 14.5 Prerequisites for packaging (why P1 work matters here)

- sounddevice instead of PyAudio (D6) avoids a hard native dependency.
- Windows OCR instead of Tesseract (D13) removes an external install.
- llama.cpp server instead of Ollama (D5) removes the biggest external install.
- Config file and %APPDATA% paths replace hardcoded "models/..." relative paths.
- Pinned versions make builds reproducible.

### 14.6 Later

Tauri 2 desktop app with the engine as a sidecar (D16), then macOS (notarization costs USD 99 per year), Linux best effort.

---

## 15. Branching and workflow

### 15.1 Model

```
main  (stable, only tested phase merges via pull request)
  \
   p1-fixes  (phase 1 integration branch)
     |- feat/timing-log
     |- fix/command-safety
     |- tune/wake-threshold
     |- perf/whisper-settings
     |- feat/sounddevice-mic
     |- feat/silero-vad
     |- feat/streaming-llm-tts
     |- feat/quick-replies-followup
     |- test/phrase-suite
     \- build/windows-installer
```

### 15.2 Rules

1. Before starting a feature branch, update it from the latest p1-fixes so it includes merged work.
2. One feature per branch, small commits, honest messages.
3. When done: describe the change in plain words, give laptop test steps, the owner tests, then merge into p1-fixes.
4. When phase 1 is complete and tested, open a pull request from p1-fixes into main.
5. Nothing is pushed or merged into main without the owner's go-ahead.
6. Branches that touch the same files (for example sounddevice-mic and silero-vad both change audio.py) are done in order, not in parallel.

### 15.3 Order and dependencies

| Order | Branch | Depends on | Main files |
|---|---|---|---|
| 1 | feat/timing-log | none | ultron.py, new timing.py |
| 2 | fix/command-safety | none | commands/*, ultron.py (sleep phrase, confirm flow) |
| 3 | tune/wake-threshold | none | config.py |
| 4 | perf/whisper-settings | timing-log (to measure) | ultron.py, config.py |
| 5 | feat/sounddevice-mic | none | audio.py, speaker.py, wakeword.py |
| 6 | feat/silero-vad | sounddevice-mic | audio.py |
| 7 | feat/streaming-llm-tts | sounddevice-mic | brain.py, speaker.py, ultron.py |
| 8 | feat/quick-replies-followup | streaming-llm-tts | speaker.py, ultron.py |
| 9 | test/phrase-suite | command-safety | tests/ |
| 10 | build/windows-installer | P1 done | packaging/, pyproject.toml, workflows |

---

## 16. Roadmap

### Phase 1: fix and speed up (now)
Safety fixes, timing log, wake threshold, Whisper settings, one mic stream, Silero VAD, warm and streaming LLM and TTS, cached replies, follow-up window, phrase suite. Then accuracy: hotwords, correction dictionary, rapidfuzz, command registry. Then features: open any installed app, "this" commands on selected text, routines, hands-free typing, Windows OCR, smaller default model.

### Phase 1b: package
pyproject and src layout, pinned versions, config file, llama.cpp server, tray, first-run wizard, PyInstaller plus Inno Setup, GitHub Actions, first public beta installer.

### Phase 2: smarter and broader
Streaming STT, model2vec intent matcher, native tool calling, active window awareness, Everything file search, caption bar, Playwright browser control, undo, auto-update.

### Phase 3: polish
Act on partial speech, speaker verification, noise suppression, echo cancellation for barge-in, Hinglish and Hindi commands, one shared sherpa-onnx speech runtime, Tauri app, macOS.

### Feature count
41 tracked features: 26 P1, 9 P2, 6 P3 (see JARVIS_improvements.xlsx).

---

## 17. Limits and non-goals

Feasible now and fast: wake word, voice commands, open, switch and close apps, folders, typing, screenshots, volume, web search, organizing files with preview and undo, launching projects, email drafts.

Feasible with limits: filling web forms (small models break action formats), explaining the screen (several seconds per screenshot on CPU), voice barge-in on laptop speakers (needs echo cancellation).

Not feasible locally on 8 GB: multi-site research with good quality, clicking arbitrary UI by vision and pixel coordinates, unattended multi-hour tasks, CAPTCHAs.

Not building first: a screenshot-and-click agent as the core, always-on full transcription, model fine-tuning, multi-agent orchestration, autonomous purchases, emails or installs, smart home, a plugin marketplace.

---

## 18. Risks and open questions

| Risk | Impact | Mitigation |
|---|---|---|
| 2B model routes commands poorly | wrong actions or more LLM fallbacks | rules first, intent matcher, tool calling with schema, confirmation |
| PyInstaller bundle large or slow to start | bad first impression | onedir, trim deps, Nuitka fallback |
| Antivirus flags unsigned exe | users cannot install | code signing (D20), submit to Microsoft for analysis |
| openWakeWord false wakes in noisy rooms | annoyance | threshold tuning, speaker verification (P3) |
| Barge-in on speakers hears its own voice | interrupts itself | wake word muted during first 0.5 s, AEC in P3, headphones recommended |
| llama.cpp GPU builds vary by machine | crashes on some PCs | CPU build always works, GPU detection with fallback |
| Model licenses | distribution issues | Apache-2.0 defaults, license shown in wizard |

Open questions:
1. Final default model: Qwen3.5 2B or Gemma 4 E2B. Decide by a routing accuracy and speed test.
2. Keep Piper high or move to medium for the Lite tier.
3. Whether to keep Ollama as a supported backend long term.
4. Product name and branding for the installer.

---

## 19. Build journal

### 2026-11-15: Audit and setup
- Read the whole repo and confirmed the stack and bugs in the project brief. Found two more: the sleep phrase is matched as a substring, and requirements.txt lists both PyAudio and sounddevice.
- The local folder was a zip download. Ran git init, linked origin, reset the index to origin/main (no file changes; the tree matched exactly), created p1-fixes.
- Added CLAUDE.md with project context, working rules, and the session handoff rule.
- Wrote this build log (design sections 2 to 18).
- Created feature branches for phase 1 (section 15).
- Next: feat/timing-log.

### 2026-11-15: Rename to ULTRON (feat/rename-ultron)
- Renamed jarvis.py to ultron.py, download_jarvis_voice.py to download_voice.py, log to ultron.log.
- New persona.py with ULTRON lines; greetings, wake, sleep and goodbye replies use it; removed "sir" from about 90 command replies; new LLM system prompt.
- Docs, README, commands.txt, templates renamed. Wake phrase still "Hey Jarvis" (D21).
- Owner approved a full cleanup, CI and a tested installer (D22).

### 2026-11-15: Command safety (fix/command-safety)
- Branch reset onto feat/rename-ultron (it had no commits of its own) so it carries the rename.
- New commands/text.py: normalize() lowercases, strips punctuation and filler words ("Ultron", "please", "now").
- New commands/risky.py: shutdown, restart and empty recycle bin moved out of system.py. Each matches only when the whole normalized sentence is one of its phrases (fullmatch regex). Fixes audit bugs 1 and 2.
- Spoken confirmation (D11): the router takes a confirm callback; ultron.py speaks "Say confirm to ...", listens up to 6 s, and runs only on "confirm" / "yes confirm" / "confirmed" / "i confirm". No callback means cancel. LLM-routed commands use the same path, and for risky ones ULTRON speaks the real result, not the model's claim (bug 5, partly).
- Typing is checked first, with a regex that tolerates "Type, hello" (bug 3).
- Sleep phrase must be the whole sentence after normalize (bug 4).
- Deleted git_organic_committer.py (D17). commands.txt updated.
- Not done here: other substring matches in system.py (for example "pause" anywhere pauses media) wait for the command registry (D10).
- Next: feat/timing-log.

### 2026-11-15: Hey Ultron wake word (feat/hey-ultron-wakeword)
- Wake phrase decided: custom openWakeWord model (D21 updated).
- config.py: default WAKE_WORD_MODEL is models/hey_ultron.onnx when the file exists, else hey_jarvis; WAKE_PHRASE drives log lines. wakeword.py warns when it falls back.
- docs/WAKE_WORD_TRAINING.md: Colab steps, file placement, test and threshold tuning, phonetic spellings and negatives if accuracy is poor.
- README and commands.txt say "Hey Ultron" with the fallback noted.
- Measured: nothing yet; waiting for the owner's trained model. Record hit rate (out of 10) and false wakes per 30 min here once tested.
- Next: tune/wake-threshold should set 0.5 for the custom model.

### 2026-11-15: Environment, voice speed and stop (feat/voice-and-stop)
- Laptop setup: venv with Python 3.11 via uv, all requirements installed, voice and wake word models downloaded, Ollama llama3.2:3b already present. requirements.txt was missing piper-tts; added on p1-fixes.
- Owner reported: text appears 2 to 3 s before the voice, some words sound wrong, and saying "stop" ran git log.
- Measured voice (before): whole reply synthesized before playback; first sound 1.35 s for the greeting, 2.2 s for a command plus quip, 3.9 s for a 3-sentence reply. Synthesis itself runs 2.5x faster than real time, so the wait was purely architectural.
- speaker.py rewritten: sounddevice output kept open, sentence-by-sentence streaming, cache for short lines, fixed persona lines pre-rendered at startup, text printed when the voice starts, instant stop through a generation counter. Measured (after): fixed lines 0.00 s, greeting 0.67 s, command plus quip 0.81 s; stop returns at once and playback ends within 0.1 s.
- tts_text.py: pronunciation fixes before synthesis (acronyms spelled out, "port 8080" as "80 80", % as percent, markdown stripped) plus a user-editable pronunciations.json. VOICE_SPEED setting, default 1.0 (the model's own default was 1.15x slower).
- Stop: "Assets stop." was Whisper mishearing "stop"; no rule matched, and the LLM invented [COMMAND: git log]. Added stop phrases (commands/text.py is_stop_phrase), commands/ai_routing.py (sentence must have 3+ words, allowlist of AI commands, git push/commit and organizing files need the key word), and ULTRON now speaks the command's real result instead of the model's text. Whisper gets hotwords for command words (WHISPER_HOTWORDS).
- Removed dead pyttsx3 settings from config.py.
- Next: hardware profiles so strong PCs get bigger, faster models and GPU use while 8 GB laptops stay light (owner request).

### 2026-11-15: Real time and date, heard-text log (fix/time-and-heard-log)
- Owner asked the time and ULTRON said 2:47 pm at about 1:05 am. The phrasing missed the 4 exact time triggers, so the LLM answered, and it has no clock.
- commands/clock.py: time and date questions matched on normalized text in many phrasings, answered from the PC clock, checked right after risky commands. Questions like "what time does the shop open" are not matched. Old exact-phrase blocks removed from general.py.
- brain.py: every LLM call gets the current local date, time and timezone in the system message (not stored in history), with an instruction never to guess. Tested: the model answered the correct time.
- ultron.py logs what it heard and the raw AI reply to ultron.log, so mishearings and invented commands can be traced.
- Built in a separate git worktree because another session was working in the main folder.

### 2026-11-15: Hardware profiles (feat/hardware-profiles)
- New hardware.py (detect and choose, D23), stt.py (load Whisper on the chosen device, warm-up transcription, CPU fallback), benchmark.py (ultron.py --benchmark). Fixed model settings removed from config.py; brain.py takes the LLM from the profile. tests/test_hardware.py covers weak, strong and tight-VRAM machines.
- CUDA check: faster-whisper failed with "cublas64_12.dll not found". Installed the NVIDIA wheels with the owner's OK, then found only cuBLAS is used (D24). requirements-gpu.txt now lists only cuBLAS.
- Measured on the laptop (GTX 1650, llama3.2:3b loaded in Ollama, 2.7 GB VRAM in use), 2.5 s spoken test clip, beam 5:
  - before: Whisper base on CPU int8, 1.34 s per command (machine had 0.65 GB RAM free)
  - after: profile GPU-4GB picks Whisper small on CUDA int8_float16, 0.53 s; base on CUDA 0.24 s; small float16 1.59 s (slower, so int8_float16 stays)
  - VRAM: 2.74 GB with the LLM, 3.10 GB with Whisper small added, of 4.0 GB. Ollama stays 100 percent on the GPU.
  - LLM: 6.7 s first reply when cold, 0.2 to 0.3 s when warm. Warming at startup (feat/streaming-llm-tts) matters.
- Next: accent benchmark.

### 2026-11-15: Accent accuracy tools (feat/accent-accuracy)
- tools/stt_benchmark.py: "record" saves 16 spoken commands to recordings/stt (git-ignored); "run" compares Whisper models on CPU and GPU with ULTRON's settings and reports word error rate, exact matches, time per command, load time and VRAM. It recommends the fastest model within 3 WER points of the best and suggests corrections.json entries with one word of context ("open pro" -> "open chrome", never "pro" -> "chrome").
- corrections.py and corrections.json: user-editable fixes for repeat mishearings, applied to every transcription in stt.py and logged. Seeded with git and VS Code mishearings.
- Tested with ULTRON's own voice as fake recordings (base 9 percent WER, base.en 36 percent on 5 phrases). The owner's real recordings are pending; their winner becomes the GPU-4GB default.
- Next: owner records, then conversation memory.

### 2026-11-15: Conversation memory (feat/conversation-memory)
- memory.py (Conversation with idle timeout and window, Facts in memory.json), commands/memory_cmds.py (remember, list, forget, forget conversation), commands/followups.py (close it, louder, quieter, again). brain.py builds each prompt from system prompt, time, facts and the recent window. ultron.py no longer resets the brain on sleep. D26.
- Measured (llama3.2:3b on GPU): "When is my standup?" answered from a saved fact; "What did I just ask you to open?" answered from the noted command, 0.88 s warm. Full 10-exchange window: 3.75 s.
- Tests: tests/test_memory.py (timeout, window, facts on disk, vague forgets ignored, follow-ups).
- Next: personal activity log.

### 2026-11-15: Personal activity log (feat/personal-log)
- activity.py (log, tracker, summariser, profile note), commands/activity_cmds.py, profile.example.md. ultron.py logs each command and marks the conversation busy so summaries wait. brain.py adds ask_once() for summaries and the profile note to every prompt. D27.
- Measured: see D27. Live summary of a simulated day took 4.2 s on llama3.2:3b.
- Tests: tests/test_activity.py (rows, speed, app time, titles not stored, exclusions, forget today, summary never sees titles, summariser waits while busy, prompt cap, voice commands).
- Next: window control, voice commit, clipboard history, push-to-talk, health check, nudges, then the connectors design.

### 2026-11-15: Faster, honest AI answers (feat/fast-honest-ai)
- D28. Tests: tests/test_streaming.py (sentence and first-clause splits, command detection).
- Measured silently on the laptop (no speakers, llama3.2:3b on GPU, Piper on CPU):
  - before: "What is the best protein powder?" full reply 3.66 s with the old prompt, then about 0.5 s to the first sound; with the 0.8 s end wait and 1 s STT, about 5 s after the user stopped. A question after idle hit the cold start (5.6 to 9.8 s).
  - after: first token 0.21 to 0.48 s when warm; first sentence ready 0.4 to 0.8 s; first audio ready 1.3 to 2.5 s (Piper about 0.13 s per word with the CPU busy); with 0.6 s end wait and 0.53 s STT (small on GPU), about 2.4 to 3.6 s after the user stopped. Model now shows "Forever" in ollama ps.
  - honesty: "specifications of my laptop" and "check my email" now get one line ("I do not have access to that information."); "why is the sky blue" and protein powder are answered.
- Not yet at the 1.0 to 1.5 s target. Remaining costs, in order: Piper time to first audio, end-of-speech wait (Silero VAD, about 0.4 s), STT model choice (base on GPU is 0.24 s; the accent benchmark decides).
- Next: system specs command, then the voice self-test harness.

### 2026-11-15: Even pauses between sentences (fix/speaker-gaps)
- Owner reported a long pause at every full stop. Cause: playback ran in the synthesis thread, so the next sentence was synthesized only after the current one finished playing. The streamed LLM answers hit the same gap.
- speaker.py now has a synthesis thread that runs up to 6 sentences ahead into a bounded queue and a player thread that writes continuously. Each sentence's edge silence is trimmed (20 ms kept) and a fixed pause added (VOICE_SENTENCE_PAUSE, 0.13 s). stop() still drops everything at once through the generation counter.
- Measured silently (fake output stream at real-time pace, 4-sentence reply): quiet stretches at full stops before 0.83, 0.73, 0.47 s; after 0.18, 0.15, 0.15 s. stop() returns at once and no audio is written after it.

### 2026-11-15: Window control, barge-in, keyword-gated AI commands (fix/ai-command-keywords, feat/window-control-bargein)
- Log review: close and minimise phrases went to the LLM (route=llm); no command existed apart from an Alt+F4 "close window" on whatever was in front. Talking over ULTRON only worked with the wake word or a key.
- commands/windows.py and tests/test_windows.py (fake window list). A read-only check of the real window list found the desktop (Progman) listed as explorer; shell and tool windows are now excluded.
- bargein.py, tests/test_bargein.py; audio.record_phrase(preroll=...) keeps the interrupting words; one "barge-in: echo level, trigger above" log line per reply for tuning.
- ai_routing: every command needs a key word (tests for "Assets stop", "wave protein", unrelated questions). corrections.json: wave/way protein -> whey protein.
- Tests: 84 pass. Not yet verified live on the laptop speakers.

### 2026-11-15: Understand any phrasing, part 1 (feat/understand-phrasing)
- D30. commands/registry.py (declarations, schema, validation, dry run), commands/router.py (stages and safety), commands/intent.py (model2vec matcher with a null class), commands/slots.py (numbers, apps, choices, cue text), commands/apps.py (alias table, fuzzy names, Start Menu index so "open <any installed app>" works). All handler modules migrated: 89 commands. commands.txt is generated (tools/gen_commands_txt.py) and tested. ai_routing.py and the [COMMAND] prompt section are gone; brain.py streams native Ollama tool calls (and catches a call written out as JSON text).
- Behaviour changes: kill port is now a confirm command; git commit, git push, close app and organize downloads are announced; the LLM-backed helpers (debug, review, translate, drafts) use ask_once so they no longer enter the conversation; non-Windows branches removed.
- Measured (laptop, silent): rules 0.03 to 0.3 ms; matcher 1.3 ms per sentence, 0.5 s model load plus 1 s index build at startup. "crank it up a bit" -> volume_up (0.88), "what were my last few commits" -> git_log (0.94), "get rid of chrome" -> asks "Did you mean: close Chrome?" (0.69); "I meant on the wave protein" (0.26), "restart the dev server" and "remind me to go to sleep at 11" reach no command.
- Tests: 87 pass (tests/test_router.py added: confirm in every stage, announce and barge-in, did-you-mean, tool-call schema checks, blocked, negatives, stage timing).
- Not done yet (part 2): tests/intents.yaml paraphrase set, tests/test_intents.py, tools/intent_eval.py, before and after accuracy, LLM comparison and the GPU-4GB default. Thresholds in router.py are the starting values from D30, not yet tuned.

### 2026-11-15: Understand any phrasing, part 2a: phrase set and accuracy (feat/understand-phrasing)
- tests/intents.yaml: 1780 paraphrases (20 per command, written by the coding model, reviewed, not copies of registry examples), 66 near-miss negatives, 48 real Heard lines (20 commands, 28 not commands). tools/intent_eval.py, tests/test_intents.py (accuracy floors, negatives never run).
- Accuracy, rules and matcher only (no LLM), same set. Weighted: heard 3, negatives 2, paraphrases 1. "Asked" = right command after "Did you mean".

| Router | Heard commands right (of 20) | Paraphrases ran right | asked right | wrong | left to LLM | Negatives clean (of 94) | Weighted |
|---|---|---|---|---|---|---|---|
| old (p1-fixes rules) | 13 | 572 | 0 | 100 | 1108 | 83 | 38.3 % |
| new (rules + matcher) | 18 (17 ran, 1 asked) | 1037 | 405 | 90 | 248 | 84 | 82.1 % |

- New: of all wrong answers, only 8 of 1894 ran the wrong command at once; the rest only asked "Did you mean" (a "no" cancels). Of the 248 left to the LLM, 214 have the right command in the tool shortlist. Rules plus matcher take about 1.6 ms per sentence.
- Guards added after reading the failures (general, not per phrase): questions about a thing ("what does git push do") do not run through the matcher; content words a command's examples never use ("restart nginx") make it ask, and stop confirm commands entirely; rules with an app parameter only claim the sentence when the app is known or installed; "write" is dictation only when no thing to compose follows; one rule for date and time in any order; Start Menu matching uses whole names.
- Known gaps: "search a file in my PC" opens a web search (no file search command yet); laptop specs have no command (next steps item B).
- Incident: an unmarked test (test_stages_are_fast) routed 200 sentences outside dry-run, so real commands ran on the laptop (window closes and minimises, focus mode mute, a screenshot on the Desktop, a pasted "hello world", a fact in the dev folder's memory.json). Fixed the test, and tests/conftest.py now forces dry-run for every test unless it is marked real_handlers.
- Next (part 2b): LLM tool stage per model, shortlist versus full tool list, the GPU-4GB default (done, see the next entry).
- Live-run fixes (owner's log 13:10 to 13:16, its Heard lines now in intents.yaml):
  - Store apps such as Claude are found through shell:AppsFolder (index built once, about 1.2 s, in a startup thread).
  - For opening only, a sound-alike match ("clod", "cloud" -> Claude) applies when exactly one installed app shares the consonants.
  - Extra words after an app name are trimmed ("clod the application by Anthropic").
  - Maximise now also brings the window to the front. "Maximise it" means the window ULTRON just minimised; "maximise everything" restores all windows.
  - New create_folder command (name, location, Desktop by default, says so if the folder exists).
  - "open chrome and search for X" searches; "3000routes" -> "3000 rupees" in corrections.json.
  - Every command's spoken result is now logged ("Command x (route, args) said: ...").
  - The barge-in line shows the measured echo and the 700 floor separately (the old line divided the floor by the factor and always showed 233).
  - Owner's 42 real commands: old 20 right, new 40 right (39 ran, 1 asked). Weighted 38.4 % -> 82.5 %. 116 tests.
  - Tradeoffs: the sound-alike match could open the wrong app when two apps share consonants, so it only acts when exactly one does. The Apps-folder scan adds 1.2 s of startup work in a background thread. "Open cloud storage" would open Claude if no "cloud storage" app exists.

### 2026-11-15: Understand any phrasing, part 2b: LLM stage comparison and the GPU-4GB default (feat/understand-phrasing)
- tools/llm_compare.py runs the sentences the rules and matcher leave to the LLM (250 of 1925, 216 of them with the right command in the shortlist) against each model with native tool calls, unloading the others first (`ollama stop`). Five vague or off-registry sentences from the owner's live run (13:31) were added as must-not-act cases (tests/intents.yaml, key llm_must_not_act, used only by this tool). A call whose arguments the registry rejects, or that holds a schema or other non-scalar, counts as malformed. Raw output: results/llm_compare_part1.log and _part2.log (not in git).
- Results (laptop GTX 1650, 4096 context, num_predict 60). "Right" = right tool among the 250 LLM-stage sentences; "wrong" = any tool call that is not the expected command, over all 1925 sentences, with the 98 negatives and the 5 vague ones shown separately.

| Model | Tools | Right (of 250) | Wrong calls, all | Wrong on negatives (of 98) | Wrong on vague (of 5) | Malformed | Median first token | VRAM (ollama ps) |
|---|---|---|---|---|---|---|---|---|
| llama3.2:3b, shortlist | yes | 162 | 76 | 34 | 2 | 44 | 1.17 s | 2.8 GB |
| llama3.2:3b, full list (89 tools) | yes | 152 | 165 | 77 | 5 | 24 | 0.78 s | 2.8 GB |
| qwen2.5:3b, shortlist | yes | 144 | 29 | 7 | 0 | 1 | 1.42 s | 2.4 GB |
| qwen3:4b, shortlist (think off) | yes | 0 counted, see below | 0 | 0 | 0 | 0 | 1.47 s | 3.6 GB |
| gemma3:4b | no: Ollama answers "does not support tools" (400) | - | - | - | - | - | - | 3.3 GB file |

- Shortlist versus full list (llama3.2:3b only): the full list made 77 wrong calls on negatives against 34 and 165 wrong in all against 76, and it lost 10 right answers; its only gain is fewer malformed arguments and a faster first token (0.78 s against 1.17 s, because the model answers less). The full list was measured on llama only: the qwen2.5:3b full-list run was stopped after more than 22 minutes as too slow, which is itself a data point against the full list (89 schemas, several thousand tokens per call on this GPU).
- qwen3:4b: with thinking switched off it still writes its reasoning into the reply ("Okay, the user wants to terminate the Zoom app. Let me check the tools...") before the tool call. With the 60-token cap used for every model no call ever arrived, so its 0 right and 0 wrong mean "no usable answer", not "perfect". A single check with 300 tokens showed it still reasoning at that length. It is also 3.6 GB. Not usable for a voice reply under 1 to 2 s, not measured further.
- Pick: GPU-4GB default is now qwen2.5:3b, then llama3.2:3b, then llama3.2:1b (hardware.py, tests/test_hardware.py). Why: it makes 29 wrong calls against llama's 76, 7 wrong on negatives against 34, 0 on the vague sentences against 2, and almost no malformed arguments (1 against 44; llama once sent the schema itself as an argument, the registry check catches that but it costs an answer). It uses 0.4 GB less VRAM (2.4 against 2.8), so Whisper small (about 0.4 GB int8_float16) stays on the GPU: the profile pick test still gives Whisper on CUDA. Cost: 18 fewer right tools (144 against 162, about 7 percent of the LLM-stage sentences, which are 13 percent of all sentences) and a first token about 0.25 s slower (1.42 against 1.17 s). A missed tool means the model answers in words, a wrong tool can act, so fewer wrong calls is worth more. If qwen2.5:3b is not installed the profile falls back to llama3.2:3b.
- Tradeoffs and better ideas:
  - The first-token times include the tool-call prompt (shortlist of at most 6 schemas); qwen2.5:3b is a little slower to start but never needed the longer outputs.
  - Chat quality was not measured: this set only tests tool choice. qwen2.5:3b answers general questions in its own style and has not been checked against the honest-AI rules and the 30-word target in config.py. Before the default ships in the installer, run the voice self-test (next steps item C) with it.
  - The matcher already ran or asked on 1479 sentences, so the model only matters for about 13 percent of them. A better fix for the remaining wrong calls than a model swap is to add a cheap post-check: when the LLM picks a tool, require the matcher score of that command to be above the TOOL_FLOOR and ask "Did you mean" when it is a confirm or announce command. Not done.
  - A fine-tuned small classifier or a no-tool pseudo-tool would reduce wrong calls further; not measured.
  - The comparison used one run per model at temperature default; differences of a few sentences are noise, the 34 against 7 gap on negatives is not.
- Not done: the 98 "asked wrong" cases (window commands, media) were not tuned in this branch; D30 thresholds are unchanged.

### 2026-11-15: Live-run fixes 2 (fix/live-run-2)
- From the owner's 13:31 to 13:36 run. D31: a tool call from the LLM passes a gate before it runs: similarity to the command's examples at least 0.50 to run, 0.47 to ask "Did you mean", below that no. Two smells weaken a match under 0.65: a content word the command never uses ("bluetooth" for volume_up) and a runner-up within 0.03. One smell asks first, two refuse; a refused request-like sentence gets an honest "I can't do that yet" instead of a wrong action.
- Measured with tools/intent_eval.py (dry run, 1920 cases): stages a and b unchanged (negatives 92 of 102 pass, heard 50 of 53 run). Of 223 positives left for the LLM with the right command on the shortlist, the gate lets 161 through (110 run, 51 ask) and stops 62 (28 percent). Negatives that could be run by some shortlisted command without asking: 44 of 44 before, 14 of 44 after. Cost: a rare paraphrase with new words now gets a question or an answer in words instead of an action.
- Repairs (router.repair, commands/context.py): "not base, best" swaps the word in the last command's text parameter and re-runs it; a complaint ("it isn't open") says what was done and offers a retry; neither picks an unrelated command, and without a previous command both fall through to normal routing. The last run and the last created folder live in commands/context.py, cleared with the conversation.
- open_folder takes any name: standard folders and their OneDrive copies, a folder inside them (two levels), the Windows Recent list, or "the new folder you just created". Malformed tool arguments (a dict as a string) raise ArgumentError. web_search drops "google for", "on google", "the web" leftovers.
- Volume: pycaw's GetSpeakers() now returns a wrapper; one helper (system._endpoint) uses its EndpointVolume and still supports the old Activate API.
- Timing: the 1961 ms for "close Chrome" was ULTRON speaking its announcement inside the rule stage, not slow routing. route() now reports rule_ms without it plus announce_ms; the Win32 wrapper is built once (it cost about 140 ms on first use) and the process-tree walk is lazy. The result line ("Closed Chrome.") is always spoken, also after an announcement.
- Noise transcripts (".", filler sounds) are ignored without asking the LLM. BARGE_IN_MIN_RMS 700 -> 200: measured echo is 0 to 8 RMS (x3 under 25), so 700 never fired; 200 is far above the echo and room noise. Each recorded phrase now logs its median and peak speech RMS ("speech level"), so the floor can be tuned from real data.
- Second batch (15:00 to 15:06 run, qwen2.5:3b). Optional app slots ("keep") are filled only from their own "except/but" clause, and one word never fills two slots. The answer to "Did you mean X?" is now yes (run), no or silence (cancel), or any other words, which are routed once as a new sentence (Reroute in router.py). Whisper gets the app names ULTRON knows plus the window verbs as hotwords, and window commands (close, minimise, maximise, switch) accept the same sound-alike app names as "open" (exactly one match). An unnamed "create folder" makes "New folder (2)" like Windows; rename_item renames the folder ULTRON just created, asks "What should I call it?" when no name is given (context.pending), and refuses paths outside the user's profile. The installed-app index (0.75 s on first use, the 422 ms "open edge") is now built in a background thread at startup. Tradeoff: "close clod" now closes Claude (announced first, so talking over it cancels). A did-you-mean round trip is still 8 to 9 s because it waits for the LLM first token, speech and a second recording; the question text is already short.
- Better ideas: restrict the shortlist by risk and group, not only similarity; train the gate floors on more of the owner's real phrases; a small "I can do X, Y, Z" help reply for refused requests.

<!-- New entries go above this line, newest last. Format:
### YYYY-MM-DD: Short title
- What changed (branch)
- Measured: before -> after
- Decisions changed
- Next
-->

---

## 20. Appendix

### 20.1 Config keys (current, environment variables)

| Key | Default | Meaning |
|---|---|---|
| ULTRON_PROFILE | auto | force Lite, CPU-Plus, GPU-4GB, GPU-8GB+ or GPU-16GB+ |
| OLLAMA_MODEL | from profile | LLM model name |
| WAKE_WORD_MODEL | hey_jarvis | built-in name or path to a model file |
| WAKE_WORD_THRESHOLD | 0.2 (to become 0.5) | wake sensitivity, higher is stricter |
| SLEEP_WORD | go to sleep | phrase that returns to sleep mode |
| WHISPER_MODEL_SIZE | from profile | tiny, base, small, medium, large-v3-turbo, .en variants or a folder |
| WHISPER_DEVICE | from profile | cpu or cuda |
| WHISPER_COMPUTE_TYPE | from profile | int8 on CPU, int8_float16 on GPU |
| WHISPER_CPU_THREADS | physical cores, max 8 | Whisper CPU threads |
| CORRECTIONS_FILE | corrections.json | mishearing fixes |
| CONVERSATION_FORGET_MINUTES | 10 | silence before the conversation is forgotten |
| CONVERSATION_MAX_EXCHANGES | 10 | exchanges sent to the LLM |
| MEMORY_FILE | memory.json | long-term facts |
| ACTIVITY_TRACKING | 1 | app tracker on or off |
| ACTIVITY_INTERVAL_SECONDS | 30 | tracker tick |
| ACTIVITY_STORE_TITLES | 0 | store window titles too |
| ACTIVITY_SUMMARIES | 1 | idle-time day summaries |
| ACTIVITY_SUMMARY_IDLE_MINUTES | 20 | idle time before a summary |
| ULTRON_DATA_DIR | data | activity database and settings |
| LLM_KEEP_ALIVE | -1 | how long Ollama keeps the model loaded (-1 forever) |
| LLM_MAX_TOKENS | 120 | cap on spoken answer length |
| END_SILENCE_SECONDS | 0.6 | pause that ends your sentence |
| VOICE_SENTENCE_PAUSE | 0.13 | pause between spoken sentences |
| WHISPER_LANGUAGE | en | fixed language to avoid noise hallucinations |
| WHISPER_VAD_FILTER | True | Whisper's own VAD (off once Silero is in) |
| SAMPLE_RATE | 16000 | required by wake word and Whisper |
| CHUNK_SIZE | 1280 | 80 ms frames |

These move into config.toml in the packaging phase, with environment variables still able to override.

### 20.2 Glossary

- Wake word: the phrase that wakes the assistant ("Hey ULTRON").
- VAD: voice activity detection, decides when you start and stop speaking.
- STT: speech to text. TTS: text to speech.
- Beam size: how many candidate transcriptions Whisper explores; 1 is greedy and fastest.
- Barge-in: interrupting the assistant while it is speaking.
- Quantization (Q4, int8): storing model weights in fewer bits to save memory and speed up CPU inference.
- Tool calling: the LLM returns a structured function call instead of free text.
- onedir: PyInstaller mode that produces a folder (faster startup than a single exe).
- Integration branch: a branch where finished features are combined and tested before going to main.

### 20.3 Laptop test checklist (fill per branch)

General before each test:
1. git switch <branch>
2. Activate the venv and run: python ultron.py
3. Wait for the greeting, then run the branch's checks below.

| Branch | Check | Pass when |
|---|---|---|
| feat/timing-log | say 5 commands | one timing line per command in the log |
| fix/command-safety | say "restart the dev server" | does not reboot; goes to LLM or says it does not know |
| fix/command-safety | say "restart my computer" | asks to confirm; saying "cancel" cancels |
| fix/command-safety | say "type restart later" | types the text, nothing else |
| fix/command-safety | say "remind me to go to sleep at 11" | does not go to sleep |
| tune/wake-threshold | 30 min of normal room noise | at most 1 false wake |
| perf/whisper-settings | same 10 commands before and after | STT median lower, accuracy same |
| feat/sounddevice-mic | wake, speak immediately | first word not clipped, no PortAudio errors |
| feat/silero-vad | short and long sentences, noisy room | ends about 0.4 s after you stop, no cut-offs |
| feat/streaming-llm-tts | ask a 3-sentence question | starts speaking after the first sentence |
| feat/quick-replies-followup | command, then a second without wake word | second is heard within 6 to 8 s |
