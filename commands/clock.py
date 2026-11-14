"""Time and date questions, answered from the PC clock.

These never go to the LLM: it has no clock and will invent a time.
Matching runs on normalized text, so "What's the time?" arrives as
"what s the time".
"""
import re
from datetime import datetime

from commands.text import normalize

_TIME_PATTERNS = [
    r"\b(what s|whats|what is) (the )?(current |exact )?time\b",
    r"\bwhat time is it\b",
    r"\b(tell|give) me the time\b",
    r"\b(current|exact) time\b",
    r"\bdo you (know|have) the time\b",
    r"\btime (is it )?(right )?now\b",
    r"^(the )?time( please)?$",
    r"\b(date|day) and (the )?time\b",
]
_DATE_PATTERNS = [
    r"\b(what s|whats|what is) (the |today s |todays )?(current )?date\b",
    r"\b(today s|todays|current) date\b",
    r"\b(what|which) day is (it|today)\b",
    r"\b(what s|whats|what is) (the )?day( today)?\b",
    r"\btell me the date\b",
    r"\bdate today\b",
    r"^(the )?date( please)?$",
    r"\btime and (the )?(date|day)\b",
]
_TIME = re.compile("|".join(_TIME_PATTERNS))
_DATE = re.compile("|".join(_DATE_PATTERNS))


def spoken_time(now: datetime) -> str:
    """'1:05 AM', without the leading zero Windows strftime cannot drop."""
    hour = now.hour % 12 or 12
    return f"{hour}:{now.minute:02d} {'AM' if now.hour < 12 else 'PM'}"


def spoken_date(now: datetime) -> str:
    """'Sunday, 15 November 2026'."""
    return f"{now:%A}, {now.day} {now:%B %Y}"


def match_clock(text: str, now: datetime | None = None) -> str | None:
    """Reply for a time or date question, or None if the text is not one."""
    norm = normalize(text)
    wants_time = bool(_TIME.search(norm))
    wants_date = bool(_DATE.search(norm))
    if not (wants_time or wants_date):
        return None
    now = now or datetime.now()
    if wants_time and wants_date:
        return f"It's {spoken_time(now)} on {spoken_date(now)}."
    if wants_time:
        return f"It's {spoken_time(now)}."
    return f"Today is {spoken_date(now)}."
