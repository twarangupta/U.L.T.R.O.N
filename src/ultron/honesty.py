"""The honesty guard (D39): the AI may not say it did something unless a command really ran.

Only commands act on the PC, and a command's own result is spoken by the router. A reply that
comes from the model in words alone therefore never describes a performed action. When one does
("Switched to VS Code.", "Closing Claude.", "Typing now."), that is a made-up claim: the sentence
is replaced with an honest line. Plain answers ("VS Code is a code editor.") pass untouched.

The check is deliberately narrow: it looks at how a sentence starts, or at "I opened ...", not at
whether a verb appears anywhere. A missed claim is possible; a blocked normal answer is worse.
"""
import re

from ultron import persona

# verb -> (past tense, -ing form)
_VERBS = {
    "open": ("opened", "opening"), "close": ("closed", "closing"), "switch": ("switched", "switching"),
    "clear": ("cleared", "clearing"), "type": ("typed", "typing"), "delete": ("deleted", "deleting"),
    "undo": ("undid|undone", "undoing"), "minimize": ("minimi[sz]ed", "minimi[sz]ing"),
    "maximize": ("maximi[sz]ed", "maximi[sz]ing"), "launch": ("launched", "launching"),
    "restore": ("restored", "restoring"), "mute": ("muted", "muting"), "unmute": ("unmuted", "unmuting"),
    "send": ("sent", "sending"), "save": ("saved", "saving"), "start": ("started", "starting"),
    "stop": ("stopped", "stopping"), "turn": ("turned", "turning"), "lock": ("locked", "locking"),
    "quit": ("quit", "quitting"), "kill": ("killed", "killing"), "scroll": ("scrolled", "scrolling"),
    "click": ("clicked", "clicking"), "press": ("pressed", "pressing"), "play": ("played", "playing"),
    "pause": ("paused", "pausing"), "raise": ("raised", "raising"), "lower": ("lowered", "lowering"),
    "increase": ("increased", "increasing"), "decrease": ("decreased", "decreasing"),
    "set": ("set", "setting"), "create": ("created", "creating"), "move": ("moved", "moving"),
    "copy": ("copied", "copying"), "paste": ("pasted", "pasting"), "write": ("wrote|written", "writing"),
    "remove": ("removed", "removing"), "enable": ("enabled", "enabling"), "disable": ("disabled", "disabling"),
    "activate": ("activated", "activating"), "focus": ("focused", "focusing"), "bring": ("brought", "bringing"),
    "run": ("ran", "running"), "try": ("tried", "trying"), "retry": ("retried", "retrying"),
    "take": ("took|taken", "taking"), "search": ("searched", "searching"), "shut": ("shut", "shutting"),
    "dim": ("dimmed", "dimming"), "adjust": ("adjusted", "adjusting"), "hide": ("hid|hidden", "hiding"),
    "show": ("showed|shown", "showing"), "go": ("went", "going"), "erase": ("erased", "erasing"),
}
_PAST = "|".join(p for p, _ in _VERBS.values())
_ING = "|".join(i for _, i in _VERBS.values())
_BASE = "|".join(_VERBS)
# At the start of a sentence only clear UI actions count: "Running every day helps" is a plain answer.
_UI = ("open", "close", "switch", "clear", "type", "delete", "undo", "minimize", "maximize", "launch", "restore",
       "mute", "unmute", "send", "save", "lock", "quit", "kill", "click", "pause", "activate", "focus", "try",
       "retry", "erase", "hide", "adjust", "shut", "paste", "copy", "scroll")
_PAST_UI = "|".join(_VERBS[v][0] for v in _UI)
_ING_UI = "|".join(_VERBS[v][1] for v in _UI)

# After these words an -ing form at the start is a noun phrase, not an action: "Closing thoughts: ..."
_NOT_ACTION = (r"thoughts?|remarks?|statements?|arguments?|credits?|ceremony|time|hours?|prices?|bell|"
               r"paragraphs?|lines?|sentences?|words?|notes?|brackets?|tags?|days?|dates?|costs?|balance|"
               r"scenes?|speeches|speech|bid|stage|act|night|week|month|year|speed|is|are|was|can|will|helps?|makes?|means|often|usually|tends")

_LEAK = re.compile(r"\(\s*ran a command[^)]*\)\s*[:,-]?\s*", re.I)

_SPEAKER = r"(?:(?:sure|okay|ok|alright|right|fine|yes)[,.!]?\s+)?"
_CLAIMS = [
    # "Switched to VS Code." / "Opened it." (not "Opened in 1999, ...")
    re.compile(rf"^{_SPEAKER}(?:{_PAST_UI})\b(?!\s+(?:in|on|by|during|since|from|at)\b)", re.I),
    # "Closing Claude." / "Typing now." / "Trying again." (not "Closing thoughts: ...")
    re.compile(rf"^{_SPEAKER}(?:{_ING_UI})\b(?!\s+(?:{_NOT_ACTION})\b)", re.I),
    # "I've closed it." / "I opened Chrome." / "I'm closing it now."
    re.compile(rf"\bI(?:'ve| have|'m| am|'ll| will| just| already)*\s+(?:just |already )?(?:{_PAST}|{_ING})\b", re.I),
    # "I'll open it." / "Let me close that." / "I can open it for you." is an offer, not a claim: not matched.
    re.compile(rf"\b(?:I'll|I will|let me|allow me to)\s+(?:{_BASE})\b", re.I),
    # "Done." / "All done." / "There you go."
    re.compile(r"^(?:all )?(?:done|finished|sorted|there you go|consider it done)\W*$", re.I),
    # "Claude isn't responding." made up from nothing
    re.compile(r"\b(?:isn't|is not|not) responding\b", re.I),
]


def strip_leaks(text: str) -> str:
    """Remove the "(ran a command)" marker the model may copy from old history."""
    return _LEAK.sub("", text)


def claims_action(sentence: str) -> bool:
    """True when the sentence says an action was done, is being done or will be done."""
    s = sentence.strip().replace("’", "'")
    return any(p.search(s) for p in _CLAIMS)


def honest_line() -> str:
    return persona.pick(persona.CANT_DO_REPLIES)


def guard_sentence(sentence: str) -> str | None:
    """The sentence to say, or None to drop it (nothing left after cleaning).

    A claim of an action is returned as None; the caller says one honest line in its place.
    """
    clean = strip_leaks(sentence).strip()
    if not clean or claims_action(clean):
        return None
    return clean


def guard_text(text: str) -> str:
    """The whole reply, with claimed actions replaced by one honest line."""
    parts = re.split(r"(?<=[.!?])\s+", strip_leaks(text).strip())
    kept, replaced = [], False
    for part in parts:
        if not part:
            continue
        if claims_action(part):
            if not replaced:
                kept.append(honest_line())
                replaced = True
        else:
            kept.append(part)
    return " ".join(kept)
