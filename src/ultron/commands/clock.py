"""Time and date questions, answered from the PC clock.

These never go to the LLM: it has no clock and will invent a time.
Matching runs on normalized text, so "What's the time?" arrives as
"what s the time".
"""
from datetime import datetime

from ultron.commands.registry import command

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
def spoken_time(now: datetime) -> str:
    """'1:05 AM', without the leading zero Windows strftime cannot drop."""
    hour = now.hour % 12 or 12
    return f"{hour}:{now.minute:02d} {'AM' if now.hour < 12 else 'PM'}"


def spoken_date(now: datetime) -> str:
    """'Sunday, 15 November 2026'."""
    return f"{now:%A}, {now.day} {now:%B %Y}"


def _reply(wants_time: bool, wants_date: bool, now: datetime | None = None) -> str:
    now = now or datetime.now()
    if wants_time and wants_date:
        return f"It's {spoken_time(now)} on {spoken_date(now)}."
    if wants_time:
        return f"It's {spoken_time(now)}."
    return f"Today is {spoken_date(now)}."


# Rules: a sentence asking for both is caught first; then time, then date.
_BOTH = (rf"(?=.*(?:{'|'.join(_TIME_PATTERNS)}))(?=.*(?:{'|'.join(_DATE_PATTERNS)})).*"
         r"|.*\b(?:date|day)\b.*\band\b.*\btime\b.*|.*\btime\b.*\band\b.*\b(?:date|day)\b.*")


@command("tell_date_and_time", "Say the current date and time from the PC clock.", group="Time and date",
         title="tell the date and time", rules=[_BOTH], priority=81,
         examples=["what's the date and time", "tell me the time and date", "day and time please",
                   "what day and time is it", "current date and time"])
def tell_date_and_time() -> str:
    return _reply(True, True)


@command("tell_time", "Say the current time from the PC clock.", group="Time and date", title="tell the time",
         rules=[rf".*(?:{'|'.join(_TIME_PATTERNS)}).*"], priority=80,
         examples=["what's the time", "what time is it", "tell me the time", "time please",
                   "do you know the time", "current time", "what is the time right now", "got the time"],
         not_examples=["how much time is left on my timer", "time to go", "what a waste of time",
                       "is it time to sleep", "how much time is being used"])
def tell_time() -> str:
    return _reply(True, False)


@command("tell_date", "Say today's date and day of the week.", group="Time and date", title="tell the date",
         rules=[rf".*(?:{'|'.join(_DATE_PATTERNS)}).*"], priority=80,
         examples=["what's the date", "what's today's date", "what day is it", "today's date",
                   "date today", "which day is today", "what is the date today"],
         not_examples=["save the date", "i have a date tonight", "what is a date fruit"])
def tell_date() -> str:
    return _reply(False, True)
