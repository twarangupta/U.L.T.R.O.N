import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import memory  # noqa: E402
from commands import memory_cmds  # noqa: E402
from commands.followups import resolve  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_conversation_survives_until_idle_timeout():
    clock = FakeClock()
    c = memory.Conversation(forget_seconds=600, max_exchanges=10, clock=clock)
    c.add_exchange("hi", "hello")
    clock.t = 599
    assert not c.expire_if_idle() and len(c) == 1
    clock.t = 599 + 601
    assert c.expire_if_idle() and len(c) == 0


def test_only_recent_exchanges_are_sent():
    c = memory.Conversation(max_exchanges=3, clock=FakeClock())
    for i in range(10):
        c.add_exchange(f"q{i}", f"a{i}")
    recent = c.recent()
    assert len(recent) == 6
    assert recent[0]["content"] == "q7" and recent[-1]["content"] == "a9"


def test_commands_are_noted_for_followups():
    c = memory.Conversation(clock=FakeClock())
    c.note_command("open chrome", "Opening Chrome.")
    assert c.last_command == "open chrome"
    assert "Opening Chrome." in c.recent()[-1]["content"]


@pytest.fixture
def facts(tmp_path, monkeypatch):
    f = memory.Facts(str(tmp_path / "memory.json"))
    monkeypatch.setattr(memory_cmds, "facts", f)
    return f


def test_remember_list_and_forget(facts):
    assert memory_cmds.match_memory("Ultron, remember that my standup is at 10.") is not None
    assert memory_cmds.match_memory("Remember my sister's name is Asha") is not None
    assert facts.all() == ["my standup is at 10", "my sister's name is Asha"]
    assert "standup" in memory_cmds.match_memory("What do you remember?")
    memory_cmds.match_memory("forget that")
    assert facts.all() == ["my standup is at 10"]
    memory_cmds.match_memory("forget about the standup")
    assert facts.all() == []
    # saved to disk and readable again
    facts.add("coffee at 4")
    assert memory.Facts(facts.path).all() == ["coffee at 4"]


def test_questions_and_vague_forgets_are_not_memory_commands(facts):
    assert memory_cmds.match_memory("do you remember what I said") is None
    assert memory_cmds.match_memory("remember when we fixed that bug") is None
    facts.add("keep me")
    assert memory_cmds.match_memory("forget about it") is None
    assert facts.all() == ["keep me"]


def test_facts_go_into_the_prompt(facts):
    facts.add("I prefer dark mode")
    assert "I prefer dark mode" in facts.prompt_note()


def test_forget_conversation_keeps_facts(facts):
    memory.conversation.add_exchange("hi", "hello")
    facts.add("keep me")
    memory_cmds.match_memory("forget this conversation")
    assert len(memory.conversation) == 0 and facts.all() == ["keep me"]


@pytest.mark.parametrize("said,last,expected", [
    ("close it", "open chrome", "close window"),
    ("Turn it up more.", "volume up", "volume up"),
    ("a bit quieter", "turn the volume up", "volume down"),
    ("again", "git status", "git status"),
    ("again", "restart my computer", None),   # risky commands are never repeated
    ("close it", "git status", None),
    ("louder", None, None),
    ("more", "open chrome", None),
])
def test_followups(said, last, expected):
    assert resolve(said, last) == expected
