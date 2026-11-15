"""Fill a command's parameters from a free sentence (stage b, the meaning matcher).

Rules (stage a) get their parameters from named regex groups; the matcher only
knows which command was meant, so the values are found here: numbers, app
names, choices and free text after a cue word.
"""
from __future__ import annotations

import re

from commands import apps
from commands.registry import Command, Param

_UNITS = {"zero": 0, "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_SCALE = {"hundred": 100, "thousand": 1000}


def find_number(text: str) -> int | None:
    """The first number in a sentence, in digits or words ("twenty five" -> 25)."""
    m = re.search(r"\d+", text)
    if m:
        return int(m.group())
    words = re.sub(r"[^a-z ]+", " ", text.lower().replace("-", " ")).split()
    total, current, seen = 0, 0, False
    for w in words:
        if w in ("a", "an") and not seen:
            continue  # "a timer" is not one; "a hundred" is handled by scale below
        if w in _UNITS:
            current += _UNITS[w]
            seen = True
        elif w in _TENS:
            current += _TENS[w]
            seen = True
        elif w in _SCALE and (seen or w == "hundred"):
            current = max(current, 1) * _SCALE[w]
            if w == "thousand":
                total, current = total + current, 0
            seen = True
        elif w == "and" and seen:
            continue
        elif seen:
            break
    return total + current if seen else None


def after_cue(text: str, cues: tuple[str, ...]) -> str | None:
    """Text after the first cue phrase ("search for cats" with cue "for" -> "cats")."""
    low = f" {text.lower()} "
    best = None
    for cue in cues:
        i = low.find(f" {cue} ")
        if i >= 0 and (best is None or i < best[0]):
            best = (i, i + len(cue) + 2)
    if best is None:
        return None
    rest = low[best[1]:].strip(" .?!,")
    return rest or None


def fill_one(p: Param, text: str):
    if p.type == "int":
        return find_number(text)
    if p.type == "app":
        found = apps.find_in_text(text)
        if found is None and p.cues:
            found = after_cue(text, p.cues)
        return found
    if p.type == "choice":
        low = f" {text.lower()} "
        for choice in sorted(p.choices, key=len, reverse=True):
            if f" {choice} " in low:
                return choice
        return None
    if p.cues:
        return after_cue(text, p.cues)
    return None


def fill(cmd: Command, text: str) -> dict:
    """Best-effort values for every param found in the sentence (may miss some)."""
    values = {}
    for p in cmd.params:
        value = fill_one(p, text)
        if value is not None:
            values[p.name] = value
    return values
