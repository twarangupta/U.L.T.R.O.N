"""Voice commands for ULTRON's memory (see memory.py).

    "remember that my standup is at 10"   save a long-term fact
    "what do you remember?"               list the facts
    "forget that"                         drop the last fact saved
    "forget that standup"                 drop facts containing those words
    "forget this conversation"            clear the conversation, keep facts
"""
import re

from ultron import persona
from ultron.commands.registry import Param, command
from ultron.memory import conversation, facts

_REMEMBER = re.compile(
    r"^\W*(?:(?:hey\s+)?(?:ultron|jarvis)\W+)?(?:please\s+)?remember\s+(?:that\s+)?(?P<fact>.+?)\W*$",
    re.IGNORECASE,
)
_NOT_A_FACT = ("when ", "what ", "how ", "where ", "who ", "why ", "me ")
_FORGET_LAST = {"forget that", "forget what i just told you", "forget the last thing", "forget the last fact"}
_FORGET_MATCHING = re.compile(r"^forget (?:that|about|the fact that) (?P<words>.+)$")
_TOO_VAGUE = {"it", "this", "that", "everything", "all"}
_GROUP = "Memory"


@command("forget_conversation", "Forget the current conversation (saved facts stay).", group=_GROUP,
         title="forget this conversation", priority=75,
         rules=["(?:forget|clear) (?:this|the|our) conversation", "(?:start a )?new conversation"],
         examples=["forget this conversation", "clear the conversation", "start a new conversation",
                   "wipe our chat", "let's start over", "fresh start please"])
def forget_conversation() -> str:
    conversation.clear()
    return persona.pick(persona.CONVERSATION_FORGOTTEN)


@command("list_memories", "Say the long-term facts ULTRON remembers.", group=_GROUP,
         title="say what you remember", priority=75,
         rules=[r"what (?:do|did|else do) you remember(?: about me)?|what have you (?:remembered|saved)"
                r"|list (?:my |your )?(?:memories|facts)|what do you know about me"],
         examples=["what do you remember", "what do you know about me", "list my memories",
                   "what have you saved about me", "tell me what you remember", "which facts do you have"],
         not_examples=["do you remember what i said", "remember when we fixed that bug"])
def list_memories() -> str:
    known = facts.all()
    if not known:
        return persona.pick(persona.MEMORY_EMPTY)
    return "I remember: " + ". ".join(known) + "."


@command("forget_last_fact", "Forget the last fact ULTRON saved.", group=_GROUP, title="forget the last fact",
         priority=75, rules=["forget that|forget what i just told you|forget the last (?:thing|fact)"],
         examples=["forget that", "forget what i just told you", "forget the last thing",
                   "delete the last fact", "scrap that last memory"])
def forget_last_fact() -> str:
    gone = facts.forget_last()
    return persona.pick(persona.MEMORY_FORGOT) if gone else persona.pick(persona.MEMORY_EMPTY)


@command("forget_fact", "Forget saved facts that contain some words.", group=_GROUP, title="forget {words}",
         params=[Param("words", "str", "words in the fact to forget", cues=("about", "that", "fact"))],
         priority=74, rules=[r"forget (?:that|about|the fact that) (?!(?:last|it|this|that|everything|all)\b)(?P<words>.+)"],
         examples=["forget about my standup", "forget that my sister is called asha",
                   "forget the fact that i like tea", "delete the memory about my car"])
def forget_fact(words: str) -> str | None:
    if words in _TOO_VAGUE:
        return None
    gone = facts.forget_matching(words)
    return persona.pick(persona.MEMORY_FORGOT) if gone else persona.pick(persona.MEMORY_NOT_FOUND)


@command("remember_fact", "Save a long-term fact about the user, said after 'remember that'.", group=_GROUP,
         title="remember {fact}", priority=73, raw=True,
         params=[Param("fact", "str", "the fact to remember, in the user's words", cues=("remember that", "remember", "note that", "keep in mind that"))],
         rules=[_REMEMBER.pattern],
         examples=["remember that my standup is at 10", "remember my sister's name is asha",
                   "remember that this project is called ultron", "please remember i drink coffee black",
                   "note that my car is a swift", "keep in mind that i work night shifts"],
         not_examples=["do you remember what i said", "remember when we fixed that bug", "remind me to call mom"])
def remember_fact(fact: str) -> str | None:
    if fact.lower().startswith(_NOT_A_FACT):
        return None
    facts.add(fact)
    return persona.pick(persona.MEMORY_SAVED)


def match_memory(text: str) -> str | None:
    """Rules-only check of the memory commands (kept for tests and old callers)."""
    from ultron.commands.router import run_rules
    return run_rules(text, group=_GROUP)
