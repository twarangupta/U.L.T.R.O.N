"""Window commands, tested against a fake window list (nothing on screen changes)."""
import pytest

from commands import windows
from commands.windows import Window, handle, parse


class FakeWindows:
    def __init__(self, wins, foreground=None, own=()):
        self.wins, self.fg, self.own = wins, foreground, set(own)
        self.calls = []

    def windows(self): return list(self.wins)
    def foreground(self): return self.fg
    def is_own(self, w): return w.hwnd in self.own
    def close(self, w): self.calls.append(("close", w.process))
    def minimise(self, w): self.calls.append(("minimise", w.process))
    def maximise(self, w): self.calls.append(("maximise", w.process))
    def focus(self, w): self.calls.append(("focus", w.process))
    def minimise_all(self): self.calls.append(("minimise_all", None))
    def restore_all(self): self.calls.append(("restore_all", None))


CHROME = Window(1, "YouTube - Google Chrome", "chrome", 10)
CODE = Window(2, "ultron.py - J.A.R.V.I.S-main - Visual Studio Code", "code", 20)
TERM = Window(3, "Windows PowerShell", "windowsterminal", 30)


def run(text, **kw):
    api = FakeWindows([CHROME, CODE, TERM], **kw)
    return handle(text, api), api.calls


def test_parse_spellings_and_phrasings():
    assert parse("Close Google Chrome.") == ("close", "google chrome", None)
    assert parse("minimise everything") == ("minimise", "everything", None)
    assert parse("Minimize everything except VS Code") == ("minimise", "everything", "vs code")
    assert parse("show desktop") == ("minimise", "everything", None)
    assert parse("restore my windows") == ("restore", None, None)
    assert parse("maximize this window") == ("maximise", "this", None)
    assert parse("what time is it") is None


def test_close_app_by_alias_and_title():
    assert run("close google chrome") == ("Closed Google Chrome.", [("close", "chrome")])
    assert run("close VS Code") == ("Closed VS Code.", [("close", "code")])
    assert run("quit visual studio code")[1] == [("close", "code")]


def test_close_app_not_open():
    assert run("close spotify")[0] == "Spotify isn't open."


def test_never_closes_itself():
    reply, calls = run("close VS Code", own={2})
    assert "close me too" in reply and calls == []
    reply, calls = run("close this window", foreground=TERM, own={3})
    assert "not closing myself" in reply and calls == []


def test_minimise_everything_and_except():
    assert run("minimize everything") == ("Everything minimised.", [("minimise_all", None)])
    reply, calls = run("minimise everything except vs code")
    assert reply == "Everything minimised except VS Code."
    assert ("minimise", "code") not in calls and ("minimise", "chrome") in calls


def test_this_window_uses_foreground():
    assert run("minimise this", foreground=CHROME)[1] == [("minimise", "chrome")]
    assert run("maximise this window", foreground=CODE)[1] == [("maximise", "code")]


def test_switch_only_claims_open_apps():
    assert run("switch to chrome")[1] == [("focus", "chrome")]
    assert run("show me my commits") == (None, [])
    assert run("kill the process on port 3000") == (None, [])


@pytest.mark.real_handlers  # the Win32 layer is faked below
def test_router_sends_close_to_windows_before_alt_f4(monkeypatch):
    from commands import execute_command
    seen = []
    monkeypatch.setattr(windows, "_Win32", lambda: FakeWindows([CHROME]))
    monkeypatch.setattr(FakeWindows, "close", lambda self, w: seen.append(w.process))
    assert execute_command("close google chrome") == "Closed Google Chrome."
    assert seen == ["chrome"]
