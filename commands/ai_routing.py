"""Which commands the LLM is allowed to trigger through a [COMMAND: x] tag.

The small model sometimes invents a command for a sentence that has nothing
to do with it. It answered a misheard "stop" with git log, and later answered
"I meant whey protein" (heard as "wave protein") with git log too. Rules:
- The user's sentence must have at least 3 words; short fragments are too
  likely to be mishearings.
- Only commands listed here can run. Anything else is ignored.
- Every command needs one of its key words in what the user actually said.
  A key word matches the start of a spoken word, so "commit" also matches
  "commits". This blocks invented commands for unrelated questions; clear
  requests ("show my git history", "turn the volume up") still work.
Risky commands (shutdown and so on) still ask for a spoken confirm on top.
"""
from commands.text import normalize

MIN_WORDS = 3

_GIT = ("git",)
_SOUND = ("volume", "sound", "audio")

# command -> key words; at least one must appear in the user's sentence
AI_COMMANDS: dict[str, tuple[str, ...]] = {
    "git status": _GIT + ("status",),
    "git log": _GIT + ("log", "commit"),
    "git branch": _GIT + ("branch",),
    "git conflicts": _GIT + ("conflict",),
    "git stash": _GIT + ("stash", "shelve"),
    "git stash pop": _GIT + ("stash", "unstash"),
    "git pull": _GIT + ("pull", "sync"),
    "git push": ("push",),
    "git commit": ("commit",),
    "lock pc": ("lock",),
    "volume up": _SOUND + ("louder",),
    "volume down": _SOUND + ("quieter", "softer"),
    "mute": _SOUND + ("mute", "silence"),
    "unmute": _SOUND + ("unmute",),
    "organize downloads": ("organize", "organise", "tidy", "sort", "clean"),
}
_SWITCH_BRANCH_KEYS = ("switch", "checkout", "branch")


def _said_any(said: list[str], keys: tuple[str, ...]) -> bool:
    return any(word.startswith(key) for word in said for key in keys)


def allowed_ai_command(transcript: str, command: str) -> bool:
    said = normalize(transcript).split()
    if len(said) < MIN_WORDS:
        return False
    cmd = normalize(command)
    if cmd.startswith("switch branch to "):
        return _said_any(said, _SWITCH_BRANCH_KEYS)
    keys = AI_COMMANDS.get(cmd)
    return keys is not None and _said_any(said, keys)
