"""Voice commands for ULTRON's memory (see memory.py).

    "remember that my standup is at 10"   save a long-term fact
    "what do you remember?"               list the facts
    "forget that"                         drop the last fact saved
    "forget that standup"                 drop facts containing those words
    "forget this conversation"            clear the conversation, keep facts
"""
import re

import persona
from commands.text import normalize
from memory import conversation, facts

_REMEMBER = re.compile(
    r"^\W*(?:(?:hey\s+)?(?:ultron|jarvis)\W+)?(?:please\s+)?remember\s+(?:that\s+)?(?P<fact>.+?)\W*$",
    re.IGNORECASE,
)
_NOT_A_FACT = ("when ", "what ", "how ", "where ", "who ", "why ", "me ")
_LIST = re.compile(r"^(what (do|did|else do) you remember( about me)?|what have you (remembered|saved)"
                   r"|list (my |your )?(memories|facts)|what do you know about me)$")
_FORGET_CONVERSATION = {
    "forget this conversation", "forget the conversation", "forget our conversation",
    "clear the conversation", "clear this conversation", "new conversation", "start a new conversation",
}
_FORGET_LAST = {"forget that", "forget what i just told you", "forget the last thing", "forget the last fact"}
_FORGET_MATCHING = re.compile(r"^forget (?:that|about|the fact that) (?P<words>.+)$")
_TOO_VAGUE = {"it", "this", "that", "everything", "all"}


def match_memory(text: str) -> str | None:
    n = normalize(text)
    if n in _FORGET_CONVERSATION:
        conversation.clear()
        return persona.pick(persona.CONVERSATION_FORGOTTEN)
    if _LIST.match(n):
        known = facts.all()
        if not known:
            return persona.pick(persona.MEMORY_EMPTY)
        return "I remember: " + ". ".join(known) + "."
    if n in _FORGET_LAST:
        gone = facts.forget_last()
        return persona.pick(persona.MEMORY_FORGOT) if gone else persona.pick(persona.MEMORY_EMPTY)
    m = _FORGET_MATCHING.match(n)
    if m and m.group("words") not in _TOO_VAGUE:
        gone = facts.forget_matching(m.group("words"))
        return persona.pick(persona.MEMORY_FORGOT) if gone else persona.pick(persona.MEMORY_NOT_FOUND)
    m = _REMEMBER.match(text.strip())
    if m and not m.group("fact").lower().startswith(_NOT_A_FACT):
        facts.add(m.group("fact"))
        return persona.pick(persona.MEMORY_SAVED)
    return None
