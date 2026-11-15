"""What ULTRON just did, so the next sentence can refer to it ("not base, best", "open the folder you just made").

Plain module state, filled by the main loop and by handlers. It is cleared with the conversation
(memory.Conversation.clear and the idle expiry), so nothing stale outlives a "forget this conversation".
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class LastRun:
    command: str
    args: dict = field(default_factory=dict)
    said: str = ""      # what the user said
    reply: str = ""     # what ULTRON answered


last_run: LastRun | None = None
pending: str | None = None          # a question ULTRON asked whose answer is the next sentence ("rename_name")
created_folder: str | None = None   # full path of the folder ULTRON created last
pending_at: float = 0.0             # when `pending` was set (monotonic), so a stale question expires


def set_pending(name: str):
    global pending, pending_at
    import time
    pending, pending_at = name, time.monotonic()


def take_pending(name: str, max_age: float = 30.0) -> bool:
    """True once if `name` was asked within max_age seconds; the question is cleared either way."""
    global pending
    import time
    hit = pending == name and time.monotonic() - pending_at <= max_age
    if pending == name:
        pending = None
    return hit


# What the user said for the commands that ran lately, oldest first: "remember this as work mode" (D37).
# Commands that work on routines, the selection or on history itself are left out.
history: deque[str] = deque(maxlen=20)
_NOT_RECORDED = ("routine", "selection")


def note_run(command: str | None, args: dict | None, said: str, reply: str | None):
    """Remember a command that ran (an LLM answer in words is not one)."""
    global last_run
    if command:
        last_run = LastRun(command, dict(args or {}), said, reply or "")
        if said and not any(word in command for word in _NOT_RECORDED):
            history.append(said)


def note_folder(path: str):
    global created_folder
    created_folder = path


def clear():
    global last_run, created_folder, pending
    last_run = created_folder = pending = None
    history.clear()
