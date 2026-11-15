"""The router's safety rules, the same for every stage (D30). Handlers run in dry-run mode."""
import pytest

import commands  # noqa: F401  (registers every command)
from commands import intent, registry, router
from commands.registry import Param, command
from commands.router import Interaction, route, run_tool_call

needs_model = pytest.mark.skipif(not intent.model_available(), reason="meaning-matcher model not downloaded")


class FakeIO(Interaction):
    def __init__(self, confirm=False, yes=False, interrupt=False):
        self._confirm, self._yes, self._interrupt = confirm, yes, interrupt
        self.prompts = []

    def confirm(self, prompt):
        self.prompts.append(("confirm", prompt))
        return self._confirm

    def ask_yes_no(self, prompt):
        self.prompts.append(("ask", prompt))
        return self._yes

    def announce(self, text):
        self.prompts.append(("announce", text))
        return self._interrupt


@pytest.fixture(autouse=True)
def dry():
    with registry.dry_run():
        yield


def ran(outcome):
    return outcome.reply is not None and outcome.reply.startswith("Would run")


# ---- confirm commands need "confirm" whichever stage picked them ----
def test_rule_stage_confirm():
    io = FakeIO(confirm=False)
    out = route("restart my computer", io)
    assert out.route == "rule" and out.command == "restart_pc" and not ran(out)
    assert io.prompts[0][0] == "confirm"
    assert ran(route("restart my computer", FakeIO(confirm=True)))


@needs_model
def test_match_stage_confirm():
    io = FakeIO(confirm=False, yes=True)  # a yes to "did you mean" is not enough
    out = route("could you switch off the pc for me", io)
    assert out.command == "shutdown_pc" and not ran(out)
    assert [kind for kind, _ in io.prompts] == ["confirm"]


def test_tool_stage_confirm():
    out = run_tool_call("restart_pc", {}, ["restart_pc"], FakeIO(confirm=False))
    assert out.route == "tool" and not ran(out)
    assert ran(run_tool_call("restart_pc", {}, ["restart_pc"], FakeIO(confirm=True)))


def test_kill_port_is_confirm():
    io = FakeIO(confirm=False)
    out = route("kill port 3000", io)
    assert out.command == "kill_port" and not ran(out) and io.prompts[0][0] == "confirm"


# ---- medium impact: announced first, talking over it cancels ----
def test_announce_then_run():
    io = FakeIO()
    out = route("close chrome", io)
    assert io.prompts == [("announce", "Closing Chrome.")] and ran(out)


def test_barge_in_on_announcement_cancels():
    out = route("git push", FakeIO(interrupt=True))
    assert out.command == "git_push" and out.reply == ""


# ---- low confidence asks "Did you mean" ----
@needs_model
def test_low_confidence_asks_first():
    io = FakeIO(yes=False)
    out = route("get rid of chrome", io)
    assert io.prompts and io.prompts[0][0] == "ask" and "close Chrome" in io.prompts[0][1]
    assert not ran(out)
    assert ran(route("get rid of chrome", FakeIO(yes=True)))


# ---- tool calls are checked against the schema and the offered list ----
def test_tool_call_must_be_offered_and_valid():
    assert run_tool_call("git_log", {}, ["volume_up"]) is None                 # not offered
    assert run_tool_call("no_such_command", {}, ["no_such_command"]) is None   # unknown
    assert run_tool_call("volume_set", {}, ["volume_set"]) is None             # missing level
    assert run_tool_call("volume_set", {"level": "loud"}, ["volume_set"]) is None
    out = run_tool_call("volume_set", {"level": "forty"}, ["volume_set"])
    assert out.args == {"level": 40} and ran(out)
    assert run_tool_call("type_text", {"text": "hi"}, ["type_text"]) is None   # dictation is rules only


def test_tool_schema_shape():
    schema = registry.get("open_folder").tool_schema()["function"]
    assert schema["name"] == "open_folder"
    assert schema["parameters"]["required"] == ["folder"]
    assert "downloads" in schema["parameters"]["properties"]["folder"]["enum"]


def test_blocked_command_never_runs():
    calls = []

    @command("format_drive_test", "Test only.", risk="blocked", rules=["format my drive"])
    def _fmt():
        calls.append(1)
        return "formatted"
    try:
        out = route("format my drive", FakeIO(confirm=True, yes=True))
        assert out.command == "format_drive_test" and calls == [] and "formatted" not in out.reply
        with registry.dry_run(False):
            assert run_tool_call("format_drive_test", {}, ["format_drive_test"], FakeIO(confirm=True)).reply != "formatted"
        assert calls == []
    finally:
        del registry.REGISTRY["format_drive_test"]


# ---- dictation and request words ----
def test_dictation_wins_over_commands():
    out = route("type restart later", FakeIO(confirm=True))
    assert out.command == "type_text" and out.args == {"text": "restart later"}


def test_request_words_are_stripped():
    assert router.clean("Can you please take a screenshot for me?") == "take a screenshot"
    assert router.clean("I said quit") == "quit"
    assert router.clean("Ultron, could you lock the screen for me") == "lock the screen"


# ---- the named negatives never trigger a command ----
NEGATIVES = ["restart the dev server", "type restart later", "remind me to go to sleep at 11",
             "Assets stop", "I meant whey protein", "I meant on the wave protein."]


@pytest.mark.parametrize("said", NEGATIVES)
def test_negatives_never_run_a_command(said):
    out = route(said, FakeIO(confirm=True, yes=True))
    if out.command == "type_text":
        return  # dictation types the words; nothing is run
    assert out.command is None, f"{said!r} -> {out.command}"
    assert "restart_pc" not in out.candidates and "shutdown_pc" not in out.candidates


GUARDED = ["don't close chrome", "do not restart my computer", "close chrome later",
           "restart my computer tomorrow", "lock the pc in 5 minutes", "never mute the sound",
           "take a screenshot after lunch"]


@pytest.mark.parametrize("said", GUARDED)
def test_negation_and_time_words_never_run_and_offer_no_tools(said):
    out = route(said, FakeIO(confirm=True, yes=True))
    # Only the timer and reminder may be offered for a deferred sentence; nothing for a negated one.
    assert out.command is None, f"{said!r} -> {out.command}"
    assert set(out.candidates) <= {"set_timer", "set_reminder"}, f"{said!r} -> {out.candidates}"


def test_guards_keep_timers_facts_and_dictation():
    assert route("set a timer for 5 minutes").command == "set_timer"
    assert route("remind me in 10 minutes to stretch").command == "set_reminder"
    assert route("remember that I do not drink coffee").command == "remember_fact"
    assert route("type don't restart").command == "type_text"


@needs_model
def test_close_second_best_asks_first():
    from commands import intent
    ranked = intent.get_matcher().rank(router.clean("make the sound a bit lower"))
    io = FakeIO(yes=False)
    out = route("make the sound a bit lower", io)
    if ranked[0].score - ranked[1].score < router.SECOND_MARGIN and out.command:
        assert io.prompts and io.prompts[0][0] == "ask"


def test_timings_are_reported():
    out = route("what is the best protein powder")
    assert "rule_ms" in out.timings
    assert out.timings["rule_ms"] < 50 and out.timings.get("match_ms", 0) < 50


def test_every_command_is_well_formed():
    for cmd in registry.REGISTRY.values():
        assert cmd.description and cmd.description.endswith(".") and len(cmd.description) < 120, cmd.name
        assert 3 <= len(cmd.examples) <= 12, cmd.name
        assert cmd.rules, f"{cmd.name} has no fast rule"
        if cmd.risk == "confirm":
            assert cmd.confirm_text, cmd.name
        for p in cmd.params:
            assert isinstance(p, Param) and p.description, f"{cmd.name}.{p.name}"
