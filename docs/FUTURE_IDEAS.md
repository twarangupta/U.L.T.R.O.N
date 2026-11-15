# ULTRON: future ideas (not for version 1)

Owner decision, 2026-11-15: do NOT build these yet. Version 1 is the Excel list (JARVIS_improvements.xlsx) plus a working Windows installer, as fast as possible. Revisit this file after the installer ships.

## 1. Use any AI server (OpenAI-compatible endpoint)
- Settings `LLM_BASE_URL` and `LLM_MODEL` in .env. Without them, ULTRON uses local Ollama as today.
- Why:
  - The bundled llama.cpp server (D24) uses the same API, so the installer can switch to it with just a different address.
  - A bigger model can run on another PC at home.
  - No lock-in to Ollama.
- Tradeoffs:
  - One more setting.
  - 5 to 20 ms of network delay, plus fallback code for when the remote PC is off.
  - Tool-call behaviour differs per server, so each server we support needs a test run.
  - Warn when the address is not local (privacy).
- Note: this may get pulled in during the installer work if llama.cpp needs it anyway.

## 2. "What's on my screen?" on request
- On "explain this error" or "what does this say": take a screenshot, then use Windows OCR (light and instant), optionally with a small local vision model (moondream2, qwen2.5-vl:3b).
- Tradeoff: the 4 GB GPU is nearly full, so a vision model would have to swap in.

## 3. Event-triggered speaking
- ULTRON speaks up only when something happens: an error dialog, a finished download, a low battery.
- Builds on nudges. No continuous screen watching (lean background goal).

## 4. Telemetry view
- Reply times, STT and LLM speed, RAM and VRAM, shown in the tray app.
- Partly overlaps with the health check from the Excel list.

## 5. More voice controls
- Interrupt sensitivity in .env and an "emotion" or intensity setting (speed and style come with the voice branch).

## 6. Custom trained ULTRON voice
- A Piper voice trained on 1 to 2 hours of recordings from a consenting speaker, with the android effect on top.
- Never a clone of a real actor.

## 7. Public name check
- "Ultron AI" (ultronai.me) is an existing product, and Ultron is a Marvel trademark.
- Fine for personal use. Consider another public name before a public release.

## 8. Wake-word custom verifier
- openWakeWord second-stage model trained on about 20 clips of the owner's voice, if "Hey Ultron" false wakes or misses stay high.

## 9. Lean mode
- Unload the LLM after 30 minutes idle on low-RAM machines (opt-in; conflicts with "never unload between commands", so idle-only).

## 10. Moved from the old CLAUDE.md queue (not in the Excel list)
- Silent voice self-test: tools/voice_selftest.py with about 60 spoken cases (Piper to 16 kHz in memory, real STT, router and LLM), report out of git. Tradeoff of dropping it: less confidence before release; the installer smoke test covers the basics.
- "Did you mean" gate when the LLM picks a command outside the matcher shortlist or one that needs confirm or announce.
- System specs command without the LLM (CPU, RAM, GPU, VRAM, Windows, disk, battery).
- Window-control leftovers: "Chrome on the left and VS Code on the right", "move this to the other screen", "minimise everything except VS Code".
- Voice commit: the LLM reads git diff, speaks a message, commits only after a spoken "confirm".
- Clipboard history with a size cap that skips secrets.
- Push-to-talk: hold a key, speak, release.
- Health check: median reply time, mic level, models, RAM and VRAM, recent errors (overlaps the telemetry view).
- Nudges: dry, rate-limited reminders from the activity log.
- Connectors (Outlook, Microsoft Graph, Gmail; read-only by default; ULTRON as an MCP client): design first and show the owner.
- Latency extras not covered by Silero VAD or streaming STT: a shorter LLM prompt for command picking, Piper first-audio speedups.
