"""Fixes from the owner's live run on 2026-11-15 (13:10 to 13:16). Nothing real runs."""
import pytest

import commands  # noqa: F401
from commands import apps, windows
from commands.router import route
from commands.windows import Window

FAKE_INDEX = {"postman": r"C:\fake\Postman.lnk", "claude": apps.APPS_FOLDER + "Claude_x!Claude",
              "microsoft edge": r"C:\fake\Microsoft Edge.lnk", "obsidian": r"C:\fake\Obsidian.lnk"}


@pytest.fixture
def fake_apps(monkeypatch):
    monkeypatch.setattr(apps, "start_menu_index", lambda: FAKE_INDEX)


@pytest.mark.parametrize("said,app", [("open postman", "postman"), ("open cloud", "claude"), ("open clod", "claude"),
                                      ("I said, open, clod the application by Anthropic", "claude")])
def test_open_installed_and_sound_alike_apps(fake_apps, said, app):
    out = route(said)
    assert out.command == "open_app", out
    assert apps.find_installed(out.args["app"])[0] == app


def test_unknown_app_is_not_claimed(fake_apps):
    assert route("open the pod bay doors").command != "open_app"


def test_search_wins_over_open():
    out = route("open google chrome and search for the best whey protein under 3000 rupees")
    assert out.command == "web_search" and out.args["query"] == "the best whey protein under 3000 rupees"


def test_rupees_correction():
    import corrections
    rules = corrections.compile_rules(corrections.load())
    assert "3000 rupees" in corrections.apply("best whey protein under 3000routes", rules)


@pytest.mark.parametrize("said,args", [
    ("create new folder on desktop, name it mouse", {"location": "desktop", "name": "mouse"}),
    ("I said create a new folder on desktop", {"location": "desktop"}),
    ("make a folder called invoices in documents", {"name": "invoices", "location": "documents"}),
])
def test_create_folder_routes(said, args):
    out = route(said)
    assert out.command == "create_folder" and out.args == args


@pytest.mark.real_handlers
def test_create_folder_makes_it_once(tmp_path, monkeypatch):
    from commands.system import create_folder
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Desktop").mkdir()
    assert create_folder("mouse") == "Created the folder mouse in Desktop."
    assert (tmp_path / "Desktop" / "mouse").is_dir()
    assert "already exists" in create_folder("mouse")


class FakeWindows:
    def __init__(self, wins, foreground=None):
        self.wins, self.fg, self.calls = wins, foreground, []

    def windows(self): return list(self.wins)
    def foreground(self): return self.fg
    def is_own(self, w): return False
    def minimise(self, w): self.calls.append(("minimise", w.process))
    def maximise(self, w): self.calls.append(("maximise", w.process))
    def focus(self, w): self.calls.append(("focus", w.process))
    def restore_all(self): self.calls.append(("restore_all", None))
    def minimise_all(self): self.calls.append(("minimise_all", None))
    def close(self, w): self.calls.append(("close", w.process))


EDGE = Window(5, "New tab - Microsoft Edge", "msedge", 50)
TERM = Window(3, "Windows PowerShell", "windowsterminal", 30)


def test_maximise_brings_window_to_front():
    api = FakeWindows([EDGE, TERM], foreground=TERM)
    assert windows.handle("maximize my microsoft edge", api) == "Microsoft Edge maximised."
    assert api.calls == [("maximise", "msedge"), ("focus", "msedge")]


def test_maximise_it_means_the_window_just_minimised():
    api = FakeWindows([EDGE, TERM], foreground=TERM)
    windows.handle("minimize microsoft edge", api)
    api.calls.clear()
    windows.handle("Maximize it again", api)
    assert api.calls == [("maximise", "msedge"), ("focus", "msedge")]


def test_maximise_everything_restores_all():
    api = FakeWindows([EDGE, TERM])
    assert windows.handle("Maximize everything", api) == "Windows restored."
    assert api.calls == [("restore_all", None)]


def test_bargein_logs_echo_and_floor_separately():
    import numpy as np
    from bargein import BargeInDetector
    b = BargeInDetector(factor=3.0, min_rms=700)
    for _ in range(10):
        b.feed(np.full(1280, 200, dtype=np.int16))
    assert round(b.echo_level()) == 200 and b.threshold() == 700
