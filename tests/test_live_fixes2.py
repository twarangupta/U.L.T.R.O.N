"""Fixes from the owner's live run on 2026-11-15 (13:31 to 13:36). Dry-run unless marked otherwise; nothing real runs."""
import time

import numpy as np
import pytest

from ultron import commands  # noqa: F401
from ultron.commands import context, registry, system
from ultron.commands.registry import ArgumentError
from ultron.commands.router import Interaction, repair, route, run_tool_call
from ultron.commands.text import is_noise


class IO(Interaction):
    def __init__(self, yes=False, announce_s=0.0):
        self.yes, self.announce_s, self.asked = yes, announce_s, []

    def ask_yes_no(self, prompt):
        self.asked.append(prompt)
        return self.yes

    def announce(self, text):
        time.sleep(self.announce_s)
        return False


@pytest.fixture(autouse=True)
def fresh_context():
    context.clear()
    yield
    context.clear()


# ---- 1. volume with the new pycaw wrapper ----
class FakeVolume:
    def __init__(self):
        self.level, self.muted = 0.5, 0

    def GetMasterVolumeLevelScalar(self):
        return self.level

    def SetMasterVolumeLevelScalar(self, v, _):
        self.level = v

    def SetMute(self, m, _):
        self.muted = m


class NewPycawDevice:  # pycaw 2024+: AudioUtilities.GetSpeakers() returns a wrapper with EndpointVolume
    def __init__(self):
        self.EndpointVolume = FakeVolume()


def test_endpoint_uses_endpoint_volume_of_the_new_wrapper():
    dev = NewPycawDevice()
    assert system._endpoint(dev) is dev.EndpointVolume


@pytest.mark.real_handlers
def test_volume_commands_work_with_the_fake_device(monkeypatch):
    vol = FakeVolume()
    monkeypatch.setattr(system, "_endpoint", lambda device=None: vol)
    system.volume_up()
    assert vol.level == pytest.approx(0.6)
    system.volume_down()
    assert vol.level == pytest.approx(0.5)
    system.volume_set(30)
    assert vol.level == pytest.approx(0.3)
    system.mute()
    assert vol.muted == 1
    system.unmute()
    assert vol.muted == 0


# ---- 2. the gate on the LLM's tool call ----
def tool(said, name, args=None, io=None):
    out = route(said)
    assert out.route == "llm", out
    return run_tool_call(name, args or {}, [name], io or IO(), scores=out.scores, sentence=out.sentence), out


def test_off_registry_request_is_refused_honestly():
    """The model called volume_up for Bluetooth: no command fits, so say so."""
    res, _ = tool("Can you turn on Bluetooth?", "volume_up")
    assert res is not None and res.route == "refused" and res.command is None
    assert "yet" in res.reply.lower()


def test_vague_remark_runs_nothing():
    res, _ = tool("it isn't open", "continue_work")
    assert res is None or res.command is None


@pytest.mark.needs_model
def test_gate_keeps_a_fitting_tool_call():
    res, out = tool("i can't hear anything, bump it up", "volume_up")
    assert res is not None and res.command == "volume_up", (res, out.scores)
    assert "bump it up" in "i can't hear anything, bump it up"


def test_gate_tiers():
    from ultron.commands.router import GATE_ASK, GATE_RUN, gate
    cmd = registry.get("volume_up")
    assert gate("make it louder", cmd, GATE_RUN, {}) == "run"
    assert gate("make it louder", cmd, (GATE_ASK + GATE_RUN) / 2, {}) == "ask"
    assert gate("make it louder", cmd, GATE_ASK - 0.01, {}) == "no"
    # one smell (an unexplained word) only asks; two smells (also a tie with another command) refuse
    assert gate("turn on bluetooth", cmd, 0.6, {}) == "ask"
    assert gate("turn on bluetooth", cmd, 0.6, {}, {"volume_up": 0.6, "mute": 0.59}) == "no"
    assert gate("turn on bluetooth", cmd, 0.9, {}) == "run"


def test_unknown_app_argument_fails_the_gate():
    res = run_tool_call("close_app", {"app": "flurbo"}, ["close_app"], IO(), scores={"close_app": 0.9},
                        sentence="close the flurbo window")
    assert res is None or res.command is None


# ---- 3. repairs ----
def test_swap_correction_reruns_last_search():
    context.note_run("web_search", {"query": "base protein powder"}, "search for base protein powder", "Searching.")
    out = repair("not base, best")
    assert out.command == "web_search" and out.args == {"query": "best protein powder"}
    assert "best protein powder" in out.reply


def test_complaint_offers_a_retry_and_reruns_on_yes():
    context.note_run("maximize_window", {"app": "vs code"}, "maximize vs code", "VS Code maximised.")
    io = IO(yes=True)
    out = repair("it didn't maximize it again", io)
    assert out.command == "maximize_window" and "VS Code maximised" in io.asked[0]
    assert "maximize_window" in out.reply  # dry run: the same command ran again


def test_complaint_declined_does_nothing():
    context.note_run("open_app", {"app": "chrome"}, "open chrome", "Opening Chrome.")
    out = repair("it isn't open", IO(yes=False))
    assert out.command == "open_app" and out.reply == ""


def test_repair_never_picks_an_unrelated_command_or_hijacks_normal_sentences():
    assert repair("it isn't open") is None  # nothing was run before
    context.note_run("web_search", {"query": "cats"}, "search for cats", "Searching.")
    for said in ("open chrome", "what time is it", "not now", "search for best protein powder", "volume up"):
        assert repair(said) is None, said
    assert repair("not dogs, birds") is None  # "dogs" is not in the last query: not a swap


# ---- 4. folders by name, malformed arguments ----
def test_find_folder_by_name_and_just_created(tmp_path):
    (tmp_path / "Desktop" / "cast").mkdir(parents=True)
    (tmp_path / "Documents" / "Taxes 2024").mkdir(parents=True)
    roots = [str(tmp_path / "Desktop"), str(tmp_path / "Documents")]
    assert system.find_folder("the cast folder", roots, []) == str(tmp_path / "Desktop" / "cast")
    assert system.find_folder("Documents", roots, []) == roots[1]
    assert system.find_folder("taxes 2024", roots, []) == str(tmp_path / "Documents" / "Taxes 2024")
    assert system.find_folder("nope", roots, []) is None
    assert system.find_folder("downloads", roots, []) is None
    context.note_folder(str(tmp_path / "Desktop" / "cast"))
    assert system.find_folder("the new folder you just created", roots, []) == str(tmp_path / "Desktop" / "cast")


def test_find_folder_in_recent_locations(tmp_path):
    (tmp_path / "elsewhere" / "Some Project").mkdir(parents=True)
    recent = [str(tmp_path / "elsewhere" / "Some Project")]
    assert system.find_folder("some project folder", [], recent) == recent[0]


@pytest.mark.parametrize("said", ["open the cast folder", "open the new folder you just created", "open my downloads"])
def test_open_folder_rules_take_any_name(said):
    assert route(said).command == "open_folder"


def test_dict_argument_is_rejected_cleanly():
    cmd = registry.get("open_folder")
    with pytest.raises(ArgumentError):
        cmd.validate({"folder": {"description": "the folder", "type": "string", "value": "cast"}})
    assert run_tool_call("open_folder", {"folder": {"type": "string"}}, ["open_folder"], IO()) is None


# ---- 5. search query leftovers ----
@pytest.mark.parametrize("raw,clean", [("google for new cars", "new cars"), ("on google new cars", "new cars"),
                                       ("the web for new cars", "new cars"), ("new cars on google", "new cars"),
                                       ("google maps for a cafe", "google maps for a cafe"),
                                       ("best protein powder", "best protein powder"), ("google", "google")])
def test_clean_query(raw, clean):
    assert system.clean_query(raw) == clean


@pytest.mark.real_handlers
def test_search_handler_cleans_the_query(monkeypatch):
    opened = []
    monkeypatch.setattr(system, "open_browser", lambda url: opened.append(url) or True)
    reply = system.web_search("google for new cars")
    assert "new cars" in reply and "google for" not in reply and opened[0].endswith("q=new%20cars")


# ---- 6. closing apps: announcing is not routing time, and a result is always said ----
def test_announcement_time_is_not_rule_time_and_result_is_said():
    out = route("close Google Chrome", IO(announce_s=0.3))
    assert out.command == "close_app"
    assert out.reply  # never ''
    assert out.timings["rule_ms"] < 100 and out.timings["announce_ms"] >= 290


# ---- 7. noise ----
@pytest.mark.parametrize("text", [".", "...", "", "  ", "?", "uh", "Um.", "hmm hmm"])
def test_noise_is_ignored(text):
    assert is_noise(text)


@pytest.mark.parametrize("text", ["stop", "a", "open it", "42"])
def test_words_are_not_noise(text):
    assert not is_noise(text)


# ---- 8. barge-in ----
def test_barge_in_floor_and_speech_level():
    from ultron import config
    from ultron.audio.bargein import BargeInDetector, speech_level
    assert config.BARGE_IN_MIN_RMS == 200
    assert speech_level([100, 300, 200]) == 200 and speech_level([]) == 0.0
    det = BargeInDetector(factor=3.0, min_rms=200, needed=4)
    for _ in range(10):
        det.feed(np.full(1280, 8, dtype=np.int16))  # the measured echo level
    assert det.threshold() == 200
