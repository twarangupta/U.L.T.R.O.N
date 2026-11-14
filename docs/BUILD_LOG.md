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

---

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
| OLLAMA_MODEL | llama3.2:3b | LLM model name |
| WAKE_WORD_MODEL | hey_jarvis | built-in name or path to a model file |
| WAKE_WORD_THRESHOLD | 0.2 (to become 0.5) | wake sensitivity, higher is stricter |
| SLEEP_WORD | go to sleep | phrase that returns to sleep mode |
| WHISPER_MODEL_SIZE | base | tiny, base, small, medium, large-v3 or a folder |
| WHISPER_DEVICE | cpu | cpu or cuda |
| WHISPER_COMPUTE_TYPE | int8 | int8 for CPU |
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
