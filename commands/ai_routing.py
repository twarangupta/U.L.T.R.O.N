"""Which commands the LLM is allowed to trigger through a [COMMAND: x] tag.

The small model sometimes invents a command for an unclear sentence (it once
answered a misheard "stop" with git log). Rules:
- The user's sentence must have at least 3 words; short fragments are too
  likely to be mishearings.
- Only commands listed here can run. Anything else is ignored.
- Commands that change things outside this PC (git push, git commit) or move
  files run only if the user actually said one of their key words.
Risky commands (shutdown and so on) still ask for a spoken confirm on top.
"""
from commands.text import normalize

MIN_WORDS = 3

# command -> key words the user must have said (empty: paraphrases are fine)
AI_COMMANDS: dict[str, tuple[str, ...]] = {
    "git status": (),
    "git log": (),
    "git branch": (),
    "git conflicts": (),
    "git stash": (),
    "git stash pop": (),
    "git pull": (),
    "lock pc": (),
    "volume up": (),
    "volume down": (),
    "mute": (),
    "unmute": (),
    "git push": ("push",),
    "git commit": ("commit",),
    "organize downloads": ("organize", "organise", "tidy", "sort", "clean"),
}


def allowed_ai_command(transcript: str, command: str) -> bool:
    said = normalize(transcript).split()
    if len(said) < MIN_WORDS:
        return False
    cmd = normalize(command)
    if cmd.startswith("switch branch to "):
        return any(w in said for w in ("switch", "checkout", "branch"))
    if cmd not in AI_COMMANDS:
        return False
    keys = AI_COMMANDS[cmd]
    return not keys or any(k in said for k in keys)
