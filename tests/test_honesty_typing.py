"""D39: the AI never claims an action it did not perform; typing, undo typing, goodbye, open-if-running,
the priority call and the short listen windows."""
import sys
import types

import pytest

from ultron import brain, config, honesty, memory, persona
from ultron.commands import context, general, registry, windows
from ultron.commands.router import route
from ultron.commands.text import is_goodbye, is_stop_phrase
from ultron.commands.windows import Window


# ---- the guard ----
@pytest.mark.parametrize("text", [
    "Switched to VS Code.", "Cleared Claude's input.", "Closed Claude.", "Claude isn't responding.", "Trying again.",
    "Typing now.", "Opening Chrome.", "I opened it.", "I've closed the window.", "I'll open that now.",
    "Sure, minimising everything.", "Done.",
])
def test_claimed_actions_are_caught(text):
    assert honesty.claims_action(text), text


@pytest.mark.parametrize("text", [
    "VS Code is a code editor.", "Closing thoughts: sleep more, worry less.", "Running every day helps your heart.",
    "Python closes files with a context manager.", "Opened in 1999, the museum is small.",
    "I can't do that yet.", "I don't have access to that.", "You could open it yourself.",
    "The door was closed.", "Chrome is a browser made by Google.", "Typing speed averages 40 words a minute.",
])
def test_plain_answers_pass(text):
    assert not honesty.claims_action(text), text


def test_leaked_marker_is_stripped():
    assert honesty.strip_leaks("(ran a command) Cleared Claude's input.") == "Cleared Claude's input."
    assert honesty.guard_sentence("(ran a command, done)") is None


def test_guard_text_replaces_only_the_claim():
    out = honesty.guard_text("Closed Claude. Anything else? Switched to VS Code.")
    assert "Closed" not in out and "Switched" not in out and "Anything else?" in out
    assert sum(line in out for line in persona.CANT_DO_REPLIES) == 1  # one honest line, not two


def _stream(monkeypatch, chunks):
    monkeypatch.setattr(brain.ollama, "chat", lambda **kw: iter(chunks))
    spoken = []
    reply = brain.StreamingReply(brain.brain, "q", spoken.append, remember=False)
    reply.join()
    return reply, spoken


def test_streamed_claim_is_replaced_by_an_honest_line(monkeypatch):
    reply, spoken = _stream(monkeypatch, [{"message": {"content": "Switched to VS Code."}}])
    assert len(spoken) == 1 and "Switched" not in spoken[0]
    assert spoken[0] in persona.CANT_DO_REPLIES
    assert reply.said == spoken[0]


def test_streamed_plain_answer_is_untouched(monkeypatch):
    _, spoken = _stream(monkeypatch, [{"message": {"content": "VS Code is a code editor. "}},
                                      {"message": {"content": "Closing thoughts: use it."}}])
    assert " ".join(spoken) == "VS Code is a code editor. Closing thoughts: use it."


def test_streamed_leak_is_stripped(monkeypatch):
    _, spoken = _stream(monkeypatch, [{"message": {"content": "(ran a command) Water is wet."}}])
    assert spoken == ["Water is wet."]


# ---- history: commands are not assistant turns ----
def test_commands_are_not_stored_as_assistant_turns():
    c = memory.Conversation()
    c.note_command("open chrome", "Opening Chrome.")
    assert c.last_command == "open chrome"
    assert c.recent() == []                      # nothing for the model to copy
    note = c.actions_note()
    assert "open chrome" in note and "Opening Chrome." in note and "(ran a command)" not in note
    c.clear()
    assert c.actions_note() == ""


def test_actions_note_is_in_the_system_prompt():
    memory.conversation.clear()
    memory.conversation._just_cleared = False  # clear() makes the next command unremembered on purpose
    memory.conversation.note_command("open chrome", "Opening Chrome.")
    msgs = brain.brain.build_messages("hi")
    assert msgs[0]["role"] == "system" and "open chrome" in msgs[0]["content"]
    assert all("ran a command" not in m["content"] for m in msgs[1:])
    memory.conversation.clear()


def test_system_prompt_forbids_pretending():
    assert "Typing now" in config.OLLAMA_SYSTEM_PROMPT and "I can't do that yet" in config.OLLAMA_SYSTEM_PROMPT


# ---- "type" alone, then the words ----
def test_type_alone_asks_then_types_the_next_sentence():
    context.clear()
    with registry.dry_run(False):  # asking is harmless; the typing itself stays in dry run
        assert route("type").reply == "Type what?"
    out = route("Hey Claude.")
    assert out.command == "type_text" and out.args["text"].rstrip(".") == "Hey Claude"


@pytest.mark.parametrize("phrase", ["type something", "start typing", "Type."])
def test_type_variants_ask(phrase):
    context.clear()
    with registry.dry_run(False):
        assert route(phrase).reply == "Type what?"


def test_pending_type_expires_and_can_be_cancelled():
    context.clear()
    context.set_pending("type_text")
    context.pending_at -= 120
    assert route("hello there").command != "type_text"
    context.set_pending("type_text")
    assert route("never mind").command == "start_typing" and context.pending is None


# ---- undo typing ----
class _Pyautogui(types.SimpleNamespace):
    def __init__(self):
        super().__init__(FAILSAFE=True, pressed=[])

    def press(self, key, presses=1, interval=0):
        self.pressed.append((key, presses))


@pytest.fixture
def fake_typing(monkeypatch):
    pg = _Pyautogui()
    monkeypatch.setitem(sys.modules, "pyautogui", pg)
    general._typed.update(chars=0, hwnd=None, process="", title="")
    return pg


def test_undo_with_nothing_typed_is_honest(fake_typing):
    assert "nothing to undo" in general.undo_typing()
    assert fake_typing.pressed == []


def test_undo_sends_exactly_that_many_backspaces(fake_typing, monkeypatch):
    claude = Window(7, "Claude", "claude", 1)
    general._typed.update(chars=11, hwnd=7, process="claude", title="Claude")
    monkeypatch.setattr(general, "_front_window", lambda: claude)
    assert "11" in general.undo_typing()
    assert fake_typing.pressed == [("backspace", 11)] and general._typed["chars"] == 0
    assert "nothing to undo" in general.undo_typing()   # a second undo does nothing


def test_undo_refuses_when_another_window_is_in_front(fake_typing, monkeypatch):
    general._typed.update(chars=5, hwnd=7, process="claude", title="Claude")
    monkeypatch.setattr(general, "_front_window", lambda: Window(9, "Notes", "notepad", 2))
    out = general.undo_typing()
    assert "isn't in front" in out and fake_typing.pressed == []
    assert general._typed["chars"] == 5


def test_undo_with_app_name_checks_the_app(fake_typing, monkeypatch):
    general._typed.update(chars=5, hwnd=9, process="notepad", title="Notes")
    monkeypatch.setattr(general, "_front_window", lambda: Window(9, "Notes", "notepad", 2))
    assert "isn't claude" in general.undo_typing("claude")
    assert fake_typing.pressed == []


@pytest.mark.parametrize("phrase", ["undo typing", "delete that", "delete what you typed", "delete the text",
                                    "undo whatever you typed in Claude"])
def test_undo_phrases_route(phrase):
    out = route(phrase)
    assert out.command == "undo_typing", (phrase, out)


def test_undo_is_not_other_deletes():
    assert route("delete the study mode routine").command == "delete_routine"
    assert route("delete the file").command != "undo_typing"


# ---- goodbye ----
@pytest.mark.parametrize("phrase", ["Goodbye.", "bye", "That's all.", "That's it for now.", "Bye bye!"])
def test_goodbye_phrases_sleep(phrase):
    assert is_goodbye(phrase) or is_stop_phrase(phrase)


def test_goodbye_is_whole_utterance_only():
    assert not is_goodbye("say goodbye to my mom") and not is_goodbye("remind me to say bye")


# ---- open an app that is already open ----
class FakeApi:
    def __init__(self, wins):
        self.wins, self.focused = wins, []

    def windows(self):
        return list(self.wins)

    def focus(self, w):
        self.focused.append(w.hwnd)


def test_bring_up_focuses_an_open_app():
    api = FakeApi([Window(1, "x - Visual Studio Code", "code", 5), Window(2, "YouTube - Chrome", "chrome", 6)])
    assert windows.bring_up("vs code", api) and api.focused == [1]


def test_bring_up_false_when_not_open_and_ignores_titles():
    api = FakeApi([Window(2, "Claude - Google Chrome", "chrome", 6)])
    assert not windows.bring_up("claude", api) and api.focused == []   # a browser tab is not the Claude app


def test_open_app_brings_up_instead_of_launching(monkeypatch):
    from ultron.commands import system
    monkeypatch.setattr(windows, "bring_up", lambda app, api=None: True)
    monkeypatch.setattr(system, "_launch", lambda app: pytest.fail("must not launch a second copy"))
    assert "already open" in system.open_app("vs code")


def test_open_app_launches_when_not_open(monkeypatch):
    from ultron.commands import system
    monkeypatch.setattr(windows, "bring_up", lambda app, api=None: False)
    monkeypatch.setattr(system, "_launch", lambda app: "Notepad")
    assert system.open_app("notepad") == "Opening Notepad."


@pytest.mark.parametrize("phrase", ["open a new chrome window", "open another vs code window",
                                    "open chrome in a new window"])
def test_new_window_phrases_route_to_the_new_window_command(phrase):
    assert route(phrase).command == "open_new_window", phrase


def test_new_window_wants_an_app_not_a_tab(monkeypatch):
    from ultron.commands import system
    monkeypatch.setattr(system, "_launch", lambda app: pytest.fail("no launch"))
    assert system.open_new_window("tab") is None
    assert route("open vs code").command == "open_app"
