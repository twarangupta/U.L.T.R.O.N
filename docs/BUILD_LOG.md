# ULTRON Build Log

(Project renamed from JARVIS to ULTRON on 2026-11-15; see D21.)

A record of how ULTRON is built, from the first audit of the repo to the shipped installer: what we decided, why, what the stack and architecture are, and what happened at each step.

Owner: Twaran Gupta
Repo: https://github.com/twarangupta/U.L.T.R.O.N (renamed from J.A.R.V.I.S on 2026-11-15)
Started: 2026-11-15
Status: Phase 1 (fixes and speed) in progress; repository cleanup done (D32)

---

## Contents

1. About this log
2. Project summary and goals
3. Starting point and audit
4. (merged into section 3)
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

## 3. Starting point and audit

Audit date: 2026-11-15, on a zip download of main (68 commits). The first version was a terminal program: openWakeWord "hey_jarvis" (threshold 0.2), faster-whisper base on the CPU (beam 5), Ollama llama3.2:3b (non-streaming, full history, routing through "[COMMAND: x]" tags), Piper synthesising the whole reply before playing it, PyAudio for both mic and speaker, hand-written substring command modules, pytesseract OCR, pip installs with ">=" versions. Estimated delay: 2 to 4 s for a built-in command, 4 to 11 s for an AI answer; about 3.6 GB of memory.

Problems found, and where they were fixed:

| # | Problem | Fixed in |
|---|---|---|
| 1 to 2 | Substring match ran shutdown, restart and empty-recycle-bin without confirmation ("type restart later" rebooted the PC) | fix/command-safety (D11) |
| 3 | Typing was checked last, so dictated words that held a command word were executed | fix/command-safety |
| 4 | "go to sleep" anywhere in a sentence slept the assistant | fix/command-safety |
| 5 | Any "COMMAND: x" in the LLM's reply ran through the substring router | D12, D30 (native tool calls), D31 (gate) |
| 6 | Wake threshold 0.2 causes false wake-ups | still open (tune/wake-threshold) |
| 7 to 8 | Mic stream reopened between modes; end of speech by raw amplitude | open (D6, D7) |
| 9 | Windows QuickEdit freezes the terminal | open |
| 10 | ">=" dependencies | pyproject.toml pins (D32) |
| 11 | git_organic_committer.py rebuilt a fake commit history | removed (D17) |

Where the time went (est.): end-of-speech wait 0.8 s, Whisper base beam 5 1 to 3 s, LLM 2 to 6 s, whole-reply TTS 0.3 to 2 s, rule match under 10 ms.

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

### D31. Gate on the LLM's tool calls
Context: a small model calls the nearest tool for anything ("it isn't open" -> continue_work, "turn on Bluetooth" -> volume_up).
Decision: a tool call runs only if the sentence resembles that command's examples (similarity at least 0.50 runs, 0.47 asks "Did you mean ...?", below that no). Two smells weaken a match under 0.65: a content word the command never uses, and a runner-up within 0.03. One smell asks first, two refuse, and a refused request gets an honest "I can't do that yet". Measured: negatives that could run unasked 44 of 44 before, 14 of 44 after; 28 percent of the right tool calls are stopped (the cost). Thresholds live in commands/router.py.

### D32. Repository layout, pinned dependencies and CI
Context: about 30 files in the root, dead code, ">=" dependencies, no CI (D22 asked for all of this).
Decision: code in `src/ultron/` (audio, stt, voice, commands, and top-level modules), editable data in `config/`, every path from `paths.py` (private files keep their old places: memory.json, data/activity.db, ultron.log, profile.md), start with `run_ultron.bat` or `python -m ultron`, dependencies pinned in pyproject.toml (core, gpu and dev extras), commands.txt became docs/COMMANDS.md, `--self-test`, and a Windows CI workflow that needs no models, GPU or audio device. No behaviour changed: 173 tests, the 1952-case intent evaluation and the command list are identical before and after. Tradeoffs: `voice/speaker.py`, `audio/capture.py` and `app.py` still create their device objects at import (the smoke test compiles them instead of importing); a lazy start would make them importable anywhere, a later change.

### D34. Live-run fixes 3: silence, announcements, Whisper retries, slow launches
Context: the live run at 20:25 on 2026-11-15 showed `record_phrase` returning 10 s of silence that Whisper transcribed every 10 s (once as "Come on, come on." after 7 s of STT), "Closing Chrome." costing 1.9 to 2.2 s before the action and "Closed Chrome." right after it, STT spikes to 2.1 s on unclear speech, and first_sound 3.9 s on web searches although rule_ms was 44 ms.
Decision: (1) the recorder returns an empty array when speech never started (preroll still counts as speech) and the app never calls Whisper on empty audio; after CONVERSATION_IDLE_SECONDS (45, env override, 0 = off) with no recognised speech ULTRON says an IDLE_REPLIES line and goes back to the wake word; the confirm and did-you-mean listens share the recorder, so they get the empty-audio rule too. (2) "doing" announcements for close_app are spoken only for apps that may hold unsaved work (editors, Office, IDEs, "this window"; list in router.py); an announced action is never followed by its "Closed X." line, an unannounced one says it afterwards; announce_ms is still logged. (3) Whisper runs at temperature 0 only; WHISPER_TEMPERATURE_FALLBACK=1 brings faster-whisper's retry ladder back; transcriptions under WHISPER_LOW_LOGPROB (-1.0) or over WHISPER_LOW_NO_SPEECH (0.6) are logged as low confidence. (4) The log now has `AI said:`, `AI tool:`, `Confirm question:` and `Did-you-mean question:` lines. (5) Commands in system.py (open app, open website, web search, open folder) hold their Popen and startfile calls until the reply is audible (first_sound_at, at most 2.5 s), or start at once when nothing will be spoken.
Tradeoffs: temperature 0 can leave a hard sentence wrong where a retry might have fixed it (but a wrong sentence at 2 s is worse than a "say that again"); the idle sleep needs 45 s of quiet, so a slow thinker loses the conversation window (the conversation memory itself survives naps); skipping the announce for browsers means talking over "Closing Chrome." can no longer cancel it (closing a browser can still restore tabs). Launch deferral works by swapping `subprocess` and `os` inside system.py for the length of one handler call, which is a few milliseconds on the main thread; only Popen and startfile are held, and `webbrowser.open` (used when Chrome is not installed) is not. Better ideas: a real VAD (feat/silero-vad) would also stop silence earlier and make the idle check exact; an explicit `launch()` helper in system.py that handlers call instead of Popen would replace the swap trick once system.py is free to edit.

---

### D33. Live-run 2 command fixes: leave focus mode, "it", sites, two requests, Bluetooth
Context: the owner's live test of dev (5a85230). Principle: every command works both as a direct command and in plain English, so each needs generous rules plus matcher examples.
Decision: (1) `meeting_mode_off` (quit, exit, stop, end, turn off focus or meeting mode, back to normal, "I'm done with my meeting"; "Asset close, focus mode" works because the rules accept a leading "asset" or "assets"); `meeting_mode` got these as not_examples so the matcher stops offering it for "Quit Focus Mode". It unmutes and restores all windows. (2) The folder ULTRON just created is kept in the command context: "open it" and "open that folder" open it, and the new `folder_location` answers "where is it" with the full path; with nothing created both return None, so the sentence goes on to the AI. (3) SITES grew from 10 to 27 (prime video, hotstar, whatsapp web, flipkart, wikipedia and others). "open X and Y" runs both when each half is a rule-matched, safe command on its own, checked first in dry run; only sentences that start with open, launch, start, close, quit or exit are considered. (4) `bluetooth_on`, `bluetooth_off` and `bluetooth_toggle` use the Windows Runtime radio API (winrt packages, about 1 MB in total, pinned in pyproject.toml); no radio gives an honest reply. (5) `normalize` removes thousands commas between digits, so "50,000" stays 50000. (6) "maximize everything" now says "Everything's back on screen."
Tradeoffs: the splitter uses rules only, so "open netflix and chrome" splits but a half that only the matcher understands does not (it falls back to today's behaviour). False splits ("search for salt and pepper", "open the salt and pepper folder") are guarded by the verb check and by requiring both halves to resolve to a real app, site or folder. Decimals like "3.5" still become "3 5" (not in scope). Better ideas: let the matcher judge the halves too once its confidence is calibrated for short phrases; a generic "undo the last mode" command.

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

### 8.5 Module layout

The code lives in `src/ultron/` (done in D32); see [ARCHITECTURE.md](ARCHITECTURE.md) for the modules and the flow diagram. Still to come in the packaging phase: `timing.py`, a tray app and first-run wizard (`ui/`), and `packaging/` (PyInstaller spec, Inno Setup script).

### 8.6 Data and config locations

- Today (D32): everything is relative to the project folder through `paths.py`: `config/` (editable data), `models/`, `data/`, `memory.json`, `profile.md`, `ultron.log`, `.env`.
- Installed target: program in C:\Program Files\ULTRON (read-only); config and user data in %APPDATA%\ULTRON; models, logs and the activity database in %LOCALAPPDATA%\ULTRON. Only `paths.py` has to change for that.

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
main  (stable; changes only at the end of a phase, through a pull request from dev)
  \
   dev  (integration branch)
     |- feat/... , fix/... , chore/...   (each starts from dev, goes into dev by pull request)
```

History: phase 1 used `p1-fixes` as the integration branch (D18); on 2026-11-15 it became `dev` (PR #4 merged p1-fixes into main, PR #5 merged the live-run fixes). The revert tag `pre-cleanup` marks main before the repository cleanup.

### 15.2 Rules

1. Start each feature branch from the latest dev; one feature per branch, small commits, honest messages.
2. When done: tests pass, the change is explained in plain words with laptop test steps, then the supervisor pushes and opens the pull request; merging needs the owner's OK.
3. Builders never push or open pull requests. Never force-push.
4. When a set of changes is tested live, open a pull request dev into main.
5. Branches that touch the same files (for example the audio branches) run in order, not in parallel.
6. CI (`.github/workflows/ci.yml`) runs ruff, pytest, the self-test and the COMMANDS.md freshness check on every push and pull request to main and dev.

### 15.3 Order of the remaining work

Voice self-test harness, latency work (shorter prompt when only picking a command, Silero VAD, Whisper base on GPU), the "ask when the LLM picks a command outside the shortlist" gate, then window layout, voice commit, clipboard history, push-to-talk, health check, nudges, connectors (design first), sounddevice mic, quick replies, and the tray app and installer.

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

All entries are from 2026-11-15, grouped by phase. Measurements are from the owner's laptop (Ryzen 6 cores, 5.9 GB RAM, GTX 1650 4 GB).

### Setup and safety (feat/rename-ultron, fix/command-safety, feat/hey-ultron-wakeword)
- Audited the repo, made the zip a git repo, wrote this log and CLAUDE.md, created the feature branches.
- Renamed JARVIS to ULTRON (persona.py, prompts, file names; "sir" removed from about 90 replies, D21). Owner approved the cleanup, CI and installer mandate (D22).
- commands/text.py normalize(), commands/risky.py: shutdown, restart and recycle bin match only the whole normalised sentence and need a spoken "confirm" (D11). Typing is checked first; the sleep phrase must be the whole sentence; git_organic_committer.py deleted (D17).
- Wake word: default model models/hey_ultron.onnx when it exists, else hey_jarvis; docs/WAKE_WORD_TRAINING.md. Waiting for the owner's trained model; tune the threshold to 0.5 then.

### Voice, stop and the clock (feat/voice-and-stop, fix/time-and-heard-log, fix/speaker-gaps)
- Laptop environment: venv on Python 3.11 with uv, voice and wake word downloaded. The owner heard text 2 to 3 s before the voice, odd pronunciations, and "stop" ran git log.
- speaker.py rewritten: persistent sounddevice output, sentence-by-sentence streaming, cache for short lines, instant stop through a generation counter. First sound: fixed lines 0.00 s, greeting 0.67 s, command plus quip 0.81 s (was 1.35 and 2.2 s). tts_text.py fixes pronunciations (acronyms, "port 8080", percent) with a user file.
- Stop phrases and Whisper hotwords added; "Assets stop" (a mishearing) no longer reaches the LLM as a command.
- Time and date: commands/clock.py answers from the PC clock in many phrasings; the LLM prompt carries the real time. What was heard and the raw AI reply are logged.
- Gaps at full stops: synthesis now runs up to 6 sentences ahead of playback, with a fixed 0.13 s pause. Quiet stretches 0.47 to 0.83 s -> 0.15 to 0.18 s.

### Hardware and speech accuracy (feat/hardware-profiles, feat/accent-accuracy)
- hardware.py picks models and devices (D23); stt.py loads Whisper on the chosen device with CPU fallback; benchmark.py. faster-whisper needed only cuBLAS (D24).
- Whisper per 2.5 s command: base CPU 1.34 s; small CUDA int8_float16 0.53 s; base CUDA 0.24 s; small float16 1.59 s. VRAM 2.74 GB with the LLM, 3.10 GB with Whisper small too, of 4.0 GB. LLM cold first reply 6.7 s, warm 0.2 to 0.3 s.
- tools/stt_benchmark.py (record 16 commands, compare models by word error rate) and config/corrections.json (user-editable fixes). The owner's own recordings are still pending; their result decides the GPU-4GB Whisper model.

### Memory, activity log and honest answers (feat/conversation-memory, feat/personal-log, feat/fast-honest-ai)
- memory.py, memory_cmds.py, followups.py (D26): conversation kept across naps, facts in memory.json. A saved fact answers "When is my standup?"; a full 10-exchange window costs 3.75 s.
- activity.py, activity_cmds.py (D27): app tracker, day summaries, profile note, "forget today"; titles are never stored by default. A simulated day summarised in 4.2 s.
- Streamed, warm, honest answers (D28). First token 0.21 to 0.48 s warm; about 2.4 to 3.6 s from the end of speech to the first audio (was about 5 s); the target 1.0 to 1.5 s is not reached. Remaining costs: Piper first audio (about 0.13 s per word), the end-of-speech wait (Silero VAD would save about 0.4 s), the STT model choice. "My laptop's specs" and "check my email" now get one honest line.

### Window control and voice interruption (fix/ai-command-keywords, feat/window-control-bargein)
- commands/windows.py (close, minimise, restore, maximise, switch; the desktop and shell windows are excluded) and audio/bargein.py (talking over ULTRON stops it; the interrupting words are kept as preroll). D29. Not yet verified live on speakers; tune BARGE_IN_FACTOR from the "barge-in" log lines.

### Understand any phrasing (feat/understand-phrasing)
- Part 1 (D30): registry, router, matcher, slots and app index; 89 commands migrated; [COMMAND] tags and ai_routing.py removed; native tool calls. Rules 0.03 to 0.3 ms, matcher 1.3 ms per sentence, 0.5 s model load plus 1 s index build at start. Kill port became a confirm command; git commit, git push, close app and organise downloads are announced first.
- Part 2a: tests/intents.yaml (1780 paraphrases, 104 negatives, the owner's real Heard lines) and tools/intent_eval.py. Weighted accuracy, rules and matcher only: old router 38.3 percent, new 82.1 percent (83.0 on the final 1952 cases); heard commands right 13 -> 18 of 20; only 8 of 1894 wrong answers ran a wrong command at once, the rest asked "Did you mean". Guards added from the failures: questions about a thing do not run, unexplained content words make it ask, app rules need a known app. Incident: an unmarked test routed 200 sentences outside dry-run and ran real commands (closes, a screenshot, a paste); tests/conftest.py now forces dry-run unless a test is marked real_handlers.
- Live-run fixes: Store apps found through shell:AppsFolder; sound-alike app names ("clod" -> Claude) only when exactly one app matches; maximise brings the window front; create_folder; every command's spoken result is logged. The owner's 42 real commands: old 20 right, new 40.
- Part 2b: LLM comparison on the 250 sentences left to the LLM. qwen2.5:3b made 29 wrong tool calls against llama3.2:3b's 76 (7 against 34 on negatives, 1 malformed against 44), uses 0.4 GB less VRAM, costs 18 fewer right tools (144 against 162) and 0.25 s more first-token time (1.42 against 1.17 s). The shortlist beat the full 89-tool list (165 wrong calls against 76). gemma3:4b has no tool support in Ollama; qwen3:4b reasons too long. GPU-4GB default is now qwen2.5:3b, then llama3.2:3b. Not measured: chat quality and the honest-AI rules on qwen2.5 (needs the voice self-test).

### Live-run fixes (fix/live-run-2, PR #5)
- D31 gate, repairs ("not base, best" swaps the word and re-runs; "it isn't open" offers a retry), open_folder by any name, pycaw volume on the new API, timing that no longer counts ULTRON's own announcement as routing time (1961 ms for "close Chrome" was speech), noise transcripts ignored, BARGE_IN_MIN_RMS 700 -> 200 (the measured echo is 0 to 8 RMS).
- Second batch: optional slots filled only from their own clause; the answer to "Did you mean?" can be a new sentence (Reroute); app names as Whisper hotwords; "New folder (2)" and rename_item; the app index built in a background thread at start. Tradeoff: "close clod" now closes Claude (announced first, so interrupting cancels). A did-you-mean round trip still takes 8 to 9 s.
- Better ideas: restrict the shortlist by risk and group; train the gate floors on more of the owner's phrases; an "I can do X, Y, Z" help reply.

### Workflow and repository cleanup (chore/cleanup)
- PR #4 (p1-fixes into main) and PR #5 merged; `dev` became the integration branch; the revert tag `pre-cleanup` marks main.
- Cleanup (D32): src/ultron layout, paths.py, pyproject.toml, CI, self-test, dead code removed (see CHANGELOG), docs rewritten. Checks before and after: 173 tests (now 215 with the smoke tests), intent_eval identical on all 1952 cases, command list identical, ruff clean.

### Live-run 2 command fixes (fix/commands-live2)
- Six fixes from the owner's live test, see D33. Checks before -> after: 215 -> 267 tests, intent_eval weighted 83.0 -> 83.2 percent (heard 60 of 68 -> 64 of 72 run at once; negatives passing 94 of 104 -> 93 of 103, the same 10 wrong), ruff clean, self-test passes, 96 commands. Dry-run only; Bluetooth was checked read-only against the real radio list, never toggled.

### Live-run fixes 3 (fix/app-live2)
- Evidence from the 20:25 run (D34). Fixed: silence no longer reaches Whisper and an idle conversation ends after 45 s; close_app announces only for apps with possible unsaved work and never says both lines; Whisper temperature fallback off by default with low-confidence logging; `AI said`, `AI tool`, confirm and did-you-mean questions are logged; app and browser launches wait for the voice.
- Measured (dry run, a 0.4 s fake browser start): reply ready after 400 ms before, under 1 ms after; the real gain on the laptop is still to be read from first_sound in the log. Tests 220 passed, 12 skipped (model not downloaded); ruff clean; self-test passes.

<!-- New entries go above this line, newest last, per phase:
### Short title (branch)
- What changed; measured before -> after; decisions changed; next
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
| CONVERSATION_IDLE_SECONDS | 45 | silence that ends a conversation (0 = off) |
| VOICE_SENTENCE_PAUSE | 0.13 | pause between spoken sentences |
| WHISPER_LANGUAGE | en | fixed language to avoid noise hallucinations |
| WHISPER_VAD_FILTER | True | Whisper's own VAD (off once Silero is in) |
| WHISPER_TEMPERATURE_FALLBACK | 0 | 1 = let Whisper retry unclear audio (slower) |
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
