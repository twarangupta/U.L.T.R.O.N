"""Short follow-ups that only make sense after the previous command.

    "open chrome" ... "close it"            -> "close window"
    "volume up"   ... "turn it up more"     -> "volume up"
    "volume up"   ... "a bit quieter"       -> "volume down"
    any command   ... "again" / "do that again" -> the same command

Pure rules, no LLM. Risky commands are never repeated this way.
"""
from commands.risky import match_risky
from commands.text import normalize

_CLOSE_IT = {"close it", "close that", "close this", "shut it", "close it again"}
_LOUDER = {"turn it up", "turn it up more", "louder", "more", "a bit more", "bit more", "a little more",
           "even louder", "more volume", "up", "higher", "turn it up a bit", "a bit louder"}
_QUIETER = {"turn it down", "turn it down more", "quieter", "less", "a bit less", "a bit quieter",
            "lower", "down", "softer", "turn it down a bit"}
_AGAIN = {"again", "do that again", "do it again", "one more time", "repeat that", "same again"}


def resolve(text: str, last_command: str | None) -> str | None:
    """The command a follow-up stands for, or None if it is not a follow-up."""
    if not last_command:
        return None
    n, last = normalize(text), normalize(last_command)
    if n in _AGAIN and match_risky(last) is None:
        return last_command
    if n in _CLOSE_IT and (last.startswith("open ") or last.startswith("launch ")):
        return "close window"
    if any(w in last.split() for w in ("volume", "mute", "unmute", "louder", "quieter")) or last in _LOUDER | _QUIETER:
        if n in _LOUDER:
            return "volume up"
        if n in _QUIETER:
            return "volume down"
    return None
