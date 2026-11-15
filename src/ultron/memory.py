"""What ULTRON remembers.

Two kinds of memory:

1. The conversation. Kept across wake-ups so "close it" or "turn it up more"
   still make sense after ULTRON dozes off. Forgotten after
   CONVERSATION_FORGET_MINUTES of silence (default 10), or when you say
   "forget this conversation". Only the last CONVERSATION_MAX_EXCHANGES
   exchanges (default 10) are sent to the LLM, so replies stay fast.
   Commands ULTRON runs are kept apart, as a note in the system prompt, never as
   assistant turns (D39), so the model cannot copy them and pretend to act.

2. Long-term facts. "Remember that my standup is at 10" saves a line to
   memory.json (plain, readable, yours to edit). Facts are included in every
   LLM prompt. "What do you remember?" lists them, "forget that" removes the
   last one, "forget that <words>" removes the matching ones.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import date

from ultron import paths
from ultron.logger import logger

FORGET_SECONDS = float(os.getenv("CONVERSATION_FORGET_MINUTES", "10")) * 60
MAX_EXCHANGES = int(os.getenv("CONVERSATION_MAX_EXCHANGES", "10"))
MEMORY_FILE = os.getenv("MEMORY_FILE", paths.MEMORY_FILE)
MAX_FACTS_IN_PROMPT = 30
MAX_ACTIONS = 4
_FILLER = {"the", "a", "an", "my", "about", "that", "of", "to", "is", "was", "i", "me"}


def _clear_context():
    from ultron.commands import context
    context.clear()


class Conversation:
    """Rolling chat history with an idle timeout. Thread-safe."""

    def __init__(self, forget_seconds: float = FORGET_SECONDS, max_exchanges: int = MAX_EXCHANGES,
                 clock=time.monotonic):
        self.forget_seconds = forget_seconds
        self.max_exchanges = max_exchanges
        self._clock = clock
        self._messages: list[dict] = []
        self._actions: list[tuple[str, str]] = []  # recent commands (what was said, what the PC answered)
        self._last = clock()
        self.last_command: str | None = None  # what the user said for the last command run
        self._just_cleared = False
        self._lock = threading.Lock()

    def expire_if_idle(self) -> bool:
        """Forget everything after a long silence. Returns True if it forgot."""
        with self._lock:
            if (self._messages or self._actions) and self._clock() - self._last > self.forget_seconds:
                self._messages.clear()
                self._actions = []
                self.last_command = None
                _clear_context()
                logger.info("Conversation forgotten after a long silence.")
                return True
            return False

    def clear(self):
        with self._lock:
            self._messages.clear()
            self._actions = []
            self.last_command = None
            _clear_context()
            self._just_cleared = True

    def add_exchange(self, user: str, assistant: str):
        with self._lock:
            self._messages += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
            # Keep a little more than we send; the rest is never needed.
            self._messages = self._messages[-4 * self.max_exchanges:]
            self._last = self._clock()

    def note_command(self, user: str, result: str):
        """Record a command ULTRON ran, so follow-ups can refer to it."""
        if self._just_cleared:  # "forget this conversation" itself is not remembered
            self._just_cleared = False
            return
        self.last_command = user
        # Not stored as an assistant turn: the model copied "(ran a command) ..." and claimed actions it never
        # performed (D39). Kept in a separate list and shown to it as a note about what the PC did.
        with self._lock:
            self._actions = (self._actions + [(user, result)])[-MAX_ACTIONS:]
            self._last = self._clock()

    def actions_note(self) -> str:
        """What the command system recently did, for the system prompt ("" when nothing)."""
        with self._lock:
            if not self._actions:
                return ""
            lines = [f"- user said {u!r}: {r or 'done'}" for u, r in self._actions]
        return ("Commands the PC ran recently. The command system did these, not you; you cannot run "
                "commands in a reply, and you must never say you did, are doing or will do an action:\n"
                + "\n".join(lines))

    def recent(self) -> list[dict]:
        """The last max_exchanges exchanges, oldest first."""
        with self._lock:
            return list(self._messages[-2 * self.max_exchanges:])

    def __len__(self):
        return len(self._messages) // 2


class Facts:
    """Long-term facts in a small JSON file."""

    def __init__(self, path: str = MEMORY_FILE):
        self.path = path
        self._facts: list[dict] = self._load()

    def _load(self) -> list[dict]:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return [x for x in data.get("facts", []) if isinstance(x, dict) and x.get("fact")]
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"Could not read {self.path}: {e}")
            return []

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"_help": "Facts ULTRON remembers. Edit freely; one fact per entry.",
                       "facts": self._facts}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def all(self) -> list[str]:
        return [x["fact"] for x in self._facts]

    def add(self, fact: str) -> str:
        fact = fact.strip().rstrip(".")
        if fact and fact.lower() not in (f.lower() for f in self.all()):
            self._facts.append({"fact": fact, "saved": date.today().isoformat()})
            self._save()
        return fact

    def forget_last(self) -> str | None:
        if not self._facts:
            return None
        gone = self._facts.pop()["fact"]
        self._save()
        return gone

    def forget_matching(self, words: str) -> list[str]:
        needle = [w for w in words.lower().split() if w not in _FILLER] or words.lower().split()
        gone = [x["fact"] for x in self._facts if all(w in x["fact"].lower() for w in needle)]
        if gone:
            self._facts = [x for x in self._facts if x["fact"] not in gone]
            self._save()
        return gone

    def prompt_note(self) -> str:
        facts = self.all()[-MAX_FACTS_IN_PROMPT:]
        if not facts:
            return ""
        return "Facts the user asked you to remember:\n" + "\n".join(f"- {f}" for f in facts)


conversation = Conversation()
facts = Facts()
