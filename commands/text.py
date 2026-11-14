"""Text clean-up shared by the command router and the main loop."""
import re

# Words people put around a command that do not change its meaning.
_LEADING_FILLERS = ("hey ultron", "ultron", "hey jarvis", "jarvis", "please", "okay", "ok")
_TRAILING_FILLERS = ("please", "now", "ultron", "jarvis")


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse spaces, strip polite filler words.

    "Ultron, restart my computer, please." -> "restart my computer"
    """
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    words = text.split()
    changed = True
    while changed and words:
        changed = False
        for filler in _LEADING_FILLERS:
            parts = filler.split()
            if words[: len(parts)] == parts:
                words = words[len(parts):]
                changed = True
        for filler in _TRAILING_FILLERS:
            parts = filler.split()
            if len(words) > len(parts) and words[-len(parts):] == parts:
                words = words[: -len(parts)]
                changed = True
    return " ".join(words)


# Saying any of these ends the conversation and puts ULTRON back to sleep.
STOP_PHRASES = {
    "stop", "stop it", "stop talking", "cancel", "never mind", "nevermind",
    "quiet", "be quiet", "shut up", "enough", "forget it", "thats all", "that s all",
}
_STOP_ENDINGS = {"stop", "cancel"}


def is_stop_phrase(text: str) -> bool:
    """True for a stop request, including short mishearings like "Assets stop."

    Longer sentences that merely end in "stop" ("add a bus stop to my notes")
    are not treated as stop requests.
    """
    words = normalize(text).split()
    if " ".join(words) in STOP_PHRASES:
        return True
    return 1 <= len(words) <= 3 and words[-1] in _STOP_ENDINGS
