# JARVIS: context for Claude sessions

Read this first in every new session. It holds the project context so a fresh session can continue without the old chat.

## Session handoff rule (from the user)
When a session's context reaches about 30 to 40 percent full, stop at a clean point and:
1. Update the "Progress log" and "Next steps" sections below so they are accurate.
2. Commit CLAUDE.md on the working branch.
3. Start a new session that begins by reading this file, and continue there.
Do not wait until the context is nearly full.

## Project
Repo: https://github.com/twarangupta/J.A.R.V.I.S (Python, Windows-first).
Goal: free, local, hands-free voice assistant that controls the PC, feels instant (under 1 s for simple commands), installs with one click, runs on 8 GB laptops, saves memory by picking smaller models (never by unloading models between commands).
Planning files (outside the repo, in the user's Downloads): JARVIS_project_brief.md, JARVIS_handover_prompt.md, JARVIS_improvements.xlsx (41 items).
Feasibility report: https://claude.ai/artifact/KNc9WgT4fuh7xvwf6EB282

## Working rules
- Work on a branch, never directly on main. Current branch: p1-fixes.
- Small, reviewable commits with honest messages.
- Ask before deleting files, rewriting history, pushing, or anything hard to undo.
- After each change, explain it in plain words and say how to test it on the laptop.
- Writing style for the user: plain text, no em dashes, light markup.
- For large changes, describe the plan before writing code.
- When something is ambiguous, ask; otherwise pick a sensible default and say which.

## Current code (verified 2026-11-15)
- jarvis.py: main loop. Wake word, then record phrase, then Whisper (beam_size=5), then execute_command, else LLM. Parses "COMMAND:" tags from the LLM reply with a regex. Sleep phrase checked by substring.
- wakeword.py: openWakeWord, "hey_jarvis", threshold from config (0.2).
- audio.py: PyAudio. start_stream/stop_stream between modes. End of speech by max amplitude > 500 and 0.8 s silence.
- brain.py: Ollama llama3.2:3b, non-streaming ollama.chat, full history; reset when going to sleep.
- config.py: env-overridable settings, system prompt with [COMMAND: x] routing.
- speaker.py: Piper models/jarvis-high.onnx, synthesizes the whole reply before playing, PyAudio output.
- commands/__init__.py: order system, git_helpers, developer, general.
- commands/system.py: line ~198 "shutdown" in text, line ~208 "restart" in text (substring, no confirmation); line ~388 empty recycle bin with no confirmation.
- commands/general.py: "type/write/insert ..." handled here, checked last, so system keywords inside typed text run first.
- git_organic_committer.py: fabricates commit history. Remove later, only after asking the user.
- requirements.txt: >= versions, includes both pyaudio and sounddevice.

## Progress log
- 2026-11-15: Folder was a zip download; ran git init, linked origin, reset to origin/main (no file changes), created branch p1-fixes. Added this CLAUDE.md.

## Next steps (P1, in order)
1. Per-stage timing log (wake, record, STT, match, act, speak).
2. Safety: whole-phrase matching for shutdown/restart/recycle bin, voice confirmation ("say confirm"), move "type ..." first in routing.
3. Wake threshold to 0.5 (env override stays).
4. Whisper settings: beam_size=1, without_timestamps, condition_on_previous_text=False.
5. One always-open mic stream (sounddevice) with a ring buffer.
6. Silero VAD end-of-speech, about 0.4 s silence.
7. Keep LLM warm, stream LLM output, speak sentence by sentence.
8. Pre-recorded common replies, follow-up window, pytest phrase suite.
