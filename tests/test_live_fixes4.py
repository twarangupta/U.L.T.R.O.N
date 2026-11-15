"""Fixes from the owner's live run of dev 5a85230 (D33). Dry-run everywhere: nothing real runs."""
import os
import sys
import types

import pytest

from ultron import commands  # noqa: F401
from ultron.commands import context, registry, router, system, windows
from ultron.commands.router import Interaction, route
from ultron.commands.text import normalize


@pytest.fixture(autouse=True)
def fresh_context():
    context.clear()
    yield
    context.clear()


def dry(said):
    with registry.dry_run():
        return route(said, Interaction(), use_matcher=False)


# ---- 1. leaving focus mode ----
@pytest.mark.parametrize("said", [
    "quit focus mode", "Quit Focus Mode", "exit meeting mode", "stop focus mode", "turn off focus mode",
    "end the meeting", "back to normal", "normal mode",
    "I'm done with my meeting", "Ultron close focus mode", "Asset close, focus mode", "Assets, exit focus mode",
    "switch off meeting mode", "focus mode off", "the meeting is over"])
def test_leave_meeting_mode(said):
    out = dry(said)
    assert out.command == "meeting_mode_off", (said, out)


@pytest.mark.parametrize("said", ["focus mode", "meeting mode", "turn on focus mode", "start meeting mode",
                                  "Asset, focus mode"])
def test_meeting_mode_still_starts(said):
    assert dry(said).command == "meeting_mode"


def test_meeting_mode_off_unmutes_and_restores(monkeypatch):
    calls = []
    monkeypatch.setattr(system, "_set_mute", lambda on: calls.append(("mute", on)))

    class Api:
        def restore_all(self):
            calls.append("restore")
    monkeypatch.setattr(windows, "_win32", lambda: Api())
    assert "off" in system.meeting_mode_off().lower()
    assert calls == [("mute", False), "restore"]


# ---- 2. "it" after create_folder ----
@pytest.mark.real_handlers
def test_open_it_after_creating_a_folder(tmp_path, monkeypatch):
    folder = tmp_path / "New folder"
    folder.mkdir()
    context.note_folder(str(folder))
    opened = []
    monkeypatch.setattr(system.subprocess, "Popen", lambda args, **k: opened.append(args))
    for said in ["open it", "open that folder", "show it", "Open the folder you just created"]:
        opened.clear()
        out = route(said, Interaction(), use_matcher=False)
        assert out.command == "open_folder", (said, out)
        assert opened and opened[0][1] == os.path.normpath(str(folder))


@pytest.mark.parametrize("said", ["where is it", "Where is the new folder you just created?",
                                  "where is the folder you just created", "where did you put the folder"])
@pytest.mark.real_handlers
def test_where_is_the_new_folder(said, tmp_path):
    context.note_folder(str(tmp_path))
    out = route(said, Interaction(), use_matcher=False)
    assert out.command == "folder_location" and str(tmp_path) in out.reply


@pytest.mark.real_handlers
def test_it_without_a_folder_is_not_ours():
    assert route("open it", Interaction(), use_matcher=False).reply is None
    assert route("where is it", Interaction(), use_matcher=False).reply is None


# ---- 3. websites and two requests ----
@pytest.mark.parametrize("said,site", [("open netflix", "netflix"), ("open prime video", "prime video"),
                                       ("go to hotstar", "hotstar"), ("open whatsapp web", "whatsapp web"),
                                       ("open flipkart", "flipkart"), ("pull up wikipedia", "wikipedia")])
def test_more_websites(said, site):
    out = dry(said)
    assert out.command == "open_website" and out.args == {"site": site}


def test_open_two_things():
    out = dry("open netflix and google chrome")
    assert "open_website" in out.reply and "open_app" in out.reply
    assert out.route == "rule"


def test_second_half_can_carry_its_own_verb():
    out = dry("open netflix and then close chrome")
    assert "open_website" in out.reply and "close_app" in out.reply


@pytest.mark.parametrize("said", [
    "search for salt and pepper", "open the salt and pepper folder", "open the cats and dogs folder",
    "open chrome and search for cats", "create a folder called salt and pepper",
    "remember that i like tea and coffee"])
def test_false_splits_are_not_made(said):
    assert router.split_request(router.clean(said)) is None, said


def test_split_needs_both_halves_to_route():
    assert router.split_request("open netflix and blorptastic") is None


# ---- 4. Bluetooth ----
@pytest.mark.parametrize("said,name", [
    ("turn on bluetooth", "bluetooth_on"), ("Can you turn on Bluetooth?", "bluetooth_on"),
    ("bluetooth off", "bluetooth_off"), ("disable bluetooth", "bluetooth_off"),
    ("turn off the bluetooth", "bluetooth_off"), ("enable bluetooth", "bluetooth_on"),
    ("toggle bluetooth", "bluetooth_toggle")])
def test_bluetooth_phrases(said, name):
    assert dry(said).command == name


def test_bluetooth_without_a_radio(monkeypatch):
    class Radios:
        @staticmethod
        async def request_access_async():
            return "allowed"

        @staticmethod
        async def get_radios_async():
            return []
    fake = types.SimpleNamespace(Radio=Radios, RadioAccessStatus=types.SimpleNamespace(ALLOWED="allowed"),
                                 RadioKind=types.SimpleNamespace(BLUETOOTH=3), RadioState=None)
    for name in ("winrt", "winrt.windows", "winrt.windows.devices"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "winrt.windows.devices.radios", fake)
    assert "no Bluetooth radio" in system.bluetooth_on()


# ---- 5. numbers keep their digits ----
def test_thousands_separator_is_kept():
    assert normalize("search for 50,000 rupees in euros") == "search for 50000 rupees in euros"
    assert normalize("1,2,3 go") == "1 2 3 go"
    out = dry("search for the price of 50,000 steps")
    assert out.args == {"query": "the price of 50000 steps"}


# ---- 6. reply wording ----
def test_maximise_everything_reply():
    class Api:
        def restore_all(self):
            pass
    assert windows.handle("maximize everything", Api()) == "Everything's back on screen."
