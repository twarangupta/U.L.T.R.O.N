"""Write docs/COMMANDS.md from the command registry (D30). Do not edit docs/COMMANDS.md by hand.

    venv\\Scripts\\python.exe tools\\gen_commands_txt.py          write it
    venv\\Scripts\\python.exe tools\\gen_commands_txt.py --check  exit 1 if it is out of date

tests/test_commands_txt.py runs the check, so a command change without a
regenerated docs/COMMANDS.md fails the tests.
"""
from __future__ import annotations

import os
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
OUT = os.path.join(ROOT, "docs", "COMMANDS.md")

HEADER = """\
================================================================================
                         ULTRON VOICE COMMANDS DIRECTORY
================================================================================

Generated from the command registry by tools/gen_commands_txt.py. Do not edit by
hand: change the command's declaration in src/ultron/commands/ and run the script again.

Wake phrase: "Hey Ultron" (custom model at models/hey_ultron.onnx, see
docs/WAKE_WORD_TRAINING.md). Until that file exists, say "Hey Jarvis" instead.
The log line "Say ... to wake me" shows which one is active.

How ULTRON understands you (D30). The phrasings below are examples, not the only
way to say things. Every sentence goes through three stages, fastest first:
  1. Rules: common phrasings, instant.
  2. Meaning: other phrasings are compared by meaning with the examples below
     (about 1 ms). A clear match runs; a close one asks "Did you mean ...?" and
     runs only if you say yes.
  3. AI: anything else goes to the local LLM, which may pick one of the closest
     commands as a tool call, or simply answers in words.

Safety, whatever stage picked a command:
  [CONFIRM]  runs only after you say "confirm" within about 6 seconds.
             Any other reply, or silence, cancels.
  [ANNOUNCE] ULTRON says what it is about to do first; talk over it to cancel.
  Dictation ("type ...") is checked first: "type restart later" types the words.

Stop: "stop", "cancel", "never mind", "quiet", "be quiet", "shut up", "enough",
"forget it" or "that's all" ends the conversation and puts ULTRON back to sleep.
Short mishearings that end in "stop" or "cancel" (up to 3 words, like "Assets stop") count too.
"Go to sleep" (the whole sentence) also sends ULTRON to sleep.

Follow-ups: after a command, "again", "close it", "louder" or "a bit quieter"
refer to the previous command. Risky commands are never repeated this way.

Interrupting: talk over ULTRON and it stops, then listens to what you said (barge-in).
The wake phrase or any key also stops it. BARGE_IN=0 turns voice interruption off.

Mishearings: if Whisper keeps hearing a word wrong (for example "get push" for
"git push"), add it to corrections.json ("what it heard": "what you said") and restart.
tools/stt_benchmark.py records your voice and suggests entries.
"""


GROUP_ORDER = ["Typing", "Windows and apps", "Media and volume", "PC status", "Time and date", "Power",
               "Git", "Developer", "Memory", "Activity log", "Utilities", "Online lookups"]


def render() -> str:
    from ultron import commands  # noqa: F401  (registers every command)
    from ultron.commands.registry import REGISTRY

    groups: dict[str, list] = {name: [] for name in GROUP_ORDER}
    for cmd in REGISTRY.values():
        groups.setdefault(cmd.group, []).append(cmd)
    groups = {name: cmds for name, cmds in groups.items() if cmds}

    lines = [HEADER]
    for number, (group, cmds) in enumerate(groups.items()):
        lines += ["-" * 80, f"{number}. {group.upper()}", "-" * 80]
        for cmd in cmds:
            tags = []
            if cmd.risk == "confirm":
                tags.append("[CONFIRM]")
            if cmd.risk == "blocked":
                tags.append("[BLOCKED]")
            if cmd.doing:
                tags.append("[ANNOUNCE]")
            if cmd.stages == ("rule",):
                tags.append("[EXACT WORDING]")
            title = (cmd.title or cmd.name.replace("_", " ")).format(**{p.name: f"<{p.name}>" for p in cmd.params})
            lines.append(f"- {title[0].upper() + title[1:]}" + (f"  {' '.join(tags)}" if tags else ""))
            lines.append(f"  * What it does: {cmd.description}")
            if cmd.params:
                names = ", ".join(f"{p.name}{'' if p.required else ' (optional)'}" for p in cmd.params)
                lines.append(f"  * You fill in: {names}")
            say = ", ".join(f'"{e}"' for e in cmd.examples)
            wrapped = textwrap.wrap(f"Say for example: {say}", width=88)
            lines.append("  * " + wrapped[0])
            lines += [f"    {w}" for w in wrapped[1:]]
            lines.append(f"  * Name: {cmd.name}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        with open(OUT, encoding="utf-8") as f:
            current = f.read()
        if current != text:
            print("docs/COMMANDS.md is out of date: run venv\\Scripts\\python.exe tools\\gen_commands_txt.py")
            return 1
        print("docs/COMMANDS.md is up to date.")
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
