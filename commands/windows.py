"""Close, minimise, maximise and switch to apps by voice (Windows only).

"close chrome", "close VS Code", "minimise everything", "minimise everything
except VS Code", "restore my windows", "maximise this", "switch to Spotify".

Apps are found among the visible top-level windows, by process name (with
common aliases) or by window title. Closing sends WM_CLOSE, the same as
clicking X, so apps can still ask to save. ULTRON never closes its own
terminal window. No LLM is involved; every action is one Win32 call.
"""
import os
import re
import sys
from dataclasses import dataclass

from commands import apps
from commands.apps import EVERYTHING as _EVERYTHING, THIS as _THIS, pretty
from commands.registry import Done, Param, command
from commands.text import normalize

APP_ALIASES = apps.APP_ALIASES  # kept here for older imports
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
_TRAILING_NOUNS = r"(?: app| application| window| windows| browser)?"

_CLOSE = rf"(?:close|quit|exit|kill) (?:the |my )?(?P<app>.+?){_TRAILING_NOUNS}"
_MINIMISE = (rf"(?:minimi[sz]e|hide) (?:the |my )?(?P<app>.+?){_TRAILING_NOUNS}"
             rf"(?: (?:except|but|other than) (?:the |my )?(?P<keep>.+?){_TRAILING_NOUNS})?")
_MAXIMISE = rf"(?:maximi[sz]e|full ?screen) (?:the |my )?(?P<app>.+?){_TRAILING_NOUNS}"
_SWITCH = rf"(?:switch to|go to|bring up|show me|focus(?: on)?) (?:the |my )?(?P<app>.+?){_TRAILING_NOUNS}"
_RESTORE = r"(?:restore|bring back|unminimi[sz]e|show) (?:all )?(?:my |the )?(?:windows|everything)"
_SHOW_DESKTOP = r"(?:show|go to) (?:the )?desktop"


@dataclass
class Window:
    hwnd: int
    title: str
    process: str  # lowercase, without .exe
    pid: int


def parse(text: str) -> tuple[str, str | None, str | None] | None:
    """Return (action, app, keep) for a window command, or None."""
    norm = normalize(text)
    if re.fullmatch(_RESTORE, norm):
        return ("restore", None, None)
    if re.fullmatch(_SHOW_DESKTOP, norm):
        return ("minimise", "everything", None)
    for action, pattern in (("close", _CLOSE), ("minimise", _MINIMISE),
                            ("maximise", _MAXIMISE), ("switch", _SWITCH)):
        m = re.fullmatch(pattern, norm)
        if m:
            app = m.group("app").strip()
            keep = m.groupdict().get("keep")
            if action == "switch" and app in _EVERYTHING | _THIS | {"desktop"}:
                return None
            return (action, app, keep.strip() if keep else None)
    return None


def matches(window: Window, app: str) -> bool:
    """Does this window belong to the app the user named?"""
    app = app.lower().strip()
    processes = APP_ALIASES.get(app) or (app.replace(" ", ""),)
    if window.process in processes:
        return True
    return len(app) >= 3 and app in window.title.lower()


def handle(text: str, windows_api=None) -> str | None:
    """Parse and run a window command; None if the text is not one. windows_api is for tests."""
    parsed = parse(text)
    if parsed is None:
        return None
    return act(*parsed, windows_api=windows_api)


def act(action: str, app: str | None, keep: str | None, windows_api=None) -> str | None:
    """Run one window action. None when the app is unknown and not open (not ours)."""
    if sys.platform != "win32" and windows_api is None:
        return "Window control only works on Windows."
    api = windows_api or _Win32()
    said_it = bool(app) and apps.clean(app) in ("it", "that")  # "maximise it", not "maximise this window"
    app = apps.canonical(app) if app else None
    keep = apps.canonical(keep) if keep else None

    if action == "restore" or (action == "maximise" and app == "everything"):
        api.restore_all()  # "maximise everything" means: bring all my windows back
        return Done("Windows restored.")
    if action == "minimise" and app in (None, "everything"):
        if keep:
            kept = [w for w in api.windows() if matches(w, keep)]
            if not kept:
                return f"{pretty(keep)} isn't open."
            for w in api.windows():
                if not matches(w, keep):
                    api.minimise(w)
            return Done(f"Everything minimised except {pretty(keep)}.")
        api.minimise_all()
        return Done("Everything minimised.")

    if said_it and action in ("maximise", "switch") and _last[0] is not None and _last_action[0] == "minimise" \
            and any(w.hwnd == _last[0].hwnd for w in api.windows()):
        target = _last[0]  # "minimise Edge" ... "maximise it": it is Edge, not whatever is in front now
        targets, name = [target], target.title.split(" - ")[-1] or "the window"
    elif app == "this":
        target = api.foreground()
        if target is None:
            return "No window to act on."
        if action == "close" and api.is_own(target):
            return "That window is running me. I'm not closing myself."
        targets = [target]
        name = target.title.split(" - ")[-1] or "the window"
    else:
        targets = [w for w in api.windows() if matches(w, app)]
        name = pretty(app)
        if not targets:
            # Only claim the sentence if it names a known app; otherwise let
            # other commands try ("show me my commits", "kill port 3000").
            return f"{name} isn't open." if app in APP_ALIASES and action != "switch" else None
        if action == "close":
            mine = [w for w in targets if api.is_own(w)]
            targets = [w for w in targets if not api.is_own(w)]
            if not targets and mine:
                return f"{name} is running me. Closing it would close me too, so no."

    if action == "close":
        for w in targets:
            api.close(w)
        _last[0] = None
        return Done(f"Closed {name}.")
    _last[0], _last_action[0] = targets[0], action
    if action == "minimise":
        for w in targets:
            api.minimise(w)
        return Done(f"{name} minimised.")
    if action == "maximise":
        api.maximise(targets[0])
        api.focus(targets[0])  # SW_MAXIMIZE alone can leave it behind other windows
        return Done(f"{name} maximised.")
    api.focus(targets[0])
    return Done(f"Switched to {name}.")


# The window ULTRON last minimised, maximised or switched to, so "maximise it" finds it.
_last: list[Window | None] = [None]
_last_action: list[str | None] = [None]


# ---- registry declarations ----
_APP = Param("app", "app", "the app, for example chrome, vs code, spotify; 'this' for the window in front",
             cues=("close", "quit", "exit", "minimise", "minimize", "maximise", "maximize", "to"))


@command("close_app", "Close an app's windows, like clicking X (the app may ask to save).",
         params=[_APP], title="close {app}", doing="Closing {app}.", group="Windows and apps",
         rules=[_CLOSE], priority=45,
         examples=["close chrome", "close google chrome", "quit spotify", "exit notepad", "close vs code",
                   "close this window", "shut chrome", "get rid of this window", "kill discord",
                   "close the browser"],
         not_examples=["close the door", "close my eyes for a minute", "how close is the moon",
                       "close the deal with the client"])
def close_app(app: str) -> str | None:
    return act("close", app, None)


@command("minimize_windows", "Minimise one app, or every window (optionally keeping one app visible).",
         params=[Param("app", "app", "the app to minimise, or 'everything'", required=False),
                 Param("keep", "app", "app to keep visible when minimising everything", required=False,
                       cues=("except", "but", "other than"))],
         title="minimise {app}", group="Windows and apps", rules=[_MINIMISE, _SHOW_DESKTOP], priority=45,
         examples=["minimise everything", "minimize all windows", "show desktop", "hide everything",
                   "minimise everything except vs code", "minimize chrome", "minimise this",
                   "hide all my windows", "clear the screen of windows"])
def minimize_windows(app: str = "everything", keep: str | None = None) -> str | None:
    if keep and app not in ("everything", None):
        app = "everything"
    return act("minimise", app, keep)


@command("restore_windows", "Bring back all minimised windows.", title="restore my windows",
         group="Windows and apps", rules=[_RESTORE], priority=46,
         examples=["restore my windows", "bring back everything", "unminimise all windows",
                   "show all windows again", "bring my windows back"])
def restore_windows() -> str:
    return act("restore", None, None)


@command("maximize_window", "Maximise an app's window, or the window in front.",
         params=[_APP], title="maximise {app}", group="Windows and apps", rules=[_MAXIMISE], priority=45,
         examples=["maximise this", "maximize chrome", "full screen vs code", "make this window bigger",
                   "make chrome full screen", "maximize the window"])
def maximize_window(app: str) -> str | None:
    return act("maximise", app, None)


@command("switch_to_app", "Bring an open app to the front.", params=[_APP], title="switch to {app}",
         group="Windows and apps", rules=[_SWITCH], priority=40,
         examples=["switch to chrome", "go to spotify", "bring up vs code", "focus on word",
                   "show me chrome", "take me to discord", "jump to my terminal"])
def switch_to_app(app: str) -> str | None:
    return act("switch", app, None)


class _Win32:
    """Thin wrapper over the Win32 calls, so the logic above can be tested."""

    def __init__(self):
        import win32con
        import win32gui
        import win32process
        self.win32con, self.win32gui, self.win32process = win32con, win32gui, win32process
        self.own_pids = _own_process_tree()

    def _window(self, hwnd: int) -> Window | None:
        import psutil
        try:
            _, pid = self.win32process.GetWindowThreadProcessId(hwnd)
            name = os.path.splitext(psutil.Process(pid).name())[0].lower()
        except Exception:
            return None
        return Window(hwnd, self.win32gui.GetWindowText(hwnd), name, pid)

    def windows(self) -> list[Window]:
        found: list[Window] = []

        def visit(hwnd, _):
            g, c = self.win32gui, self.win32con
            if g.GetClassName(hwnd) in _SHELL_CLASSES:
                return True  # the desktop and taskbar: closing Progman opens "Shut down Windows"
            if g.GetWindowLong(hwnd, c.GWL_EXSTYLE) & c.WS_EX_TOOLWINDOW:
                return True  # overlays and floating tool windows
            if g.IsWindowVisible(hwnd) and g.GetWindowText(hwnd) and not g.GetWindow(hwnd, c.GW_OWNER):
                w = self._window(hwnd)
                if w and w.process not in {"textinputhost", "applicationframehost", "shellexperiencehost"}:
                    found.append(w)
            return True

        self.win32gui.EnumWindows(visit, None)
        return found

    def foreground(self) -> Window | None:
        hwnd = self.win32gui.GetForegroundWindow()
        return self._window(hwnd) if hwnd else None

    def is_own(self, w: Window) -> bool:
        return w.pid in self.own_pids or w.hwnd == _console_window()

    def close(self, w: Window):
        self.win32gui.PostMessage(w.hwnd, self.win32con.WM_CLOSE, 0, 0)

    def minimise(self, w: Window):
        self.win32gui.ShowWindow(w.hwnd, self.win32con.SW_MINIMIZE)

    def maximise(self, w: Window):
        self.win32gui.ShowWindow(w.hwnd, self.win32con.SW_MAXIMIZE)

    def focus(self, w: Window):
        g, c = self.win32gui, self.win32con
        if g.IsIconic(w.hwnd):
            g.ShowWindow(w.hwnd, c.SW_RESTORE)
        try:
            import win32api
            win32api.keybd_event(c.VK_MENU, 0, 0, 0)  # an Alt tap lets us take the foreground
            win32api.keybd_event(c.VK_MENU, 0, c.KEYEVENTF_KEYUP, 0)
            g.SetForegroundWindow(w.hwnd)
        except Exception:
            g.ShowWindow(w.hwnd, c.SW_SHOW)

    def minimise_all(self):
        import win32com.client
        win32com.client.Dispatch("Shell.Application").MinimizeAll()

    def restore_all(self):
        import win32com.client
        win32com.client.Dispatch("Shell.Application").UndoMinimizeALL()


def _own_process_tree() -> set[int]:
    import psutil
    pids = {os.getpid()}
    try:
        for parent in psutil.Process().parents():
            if parent.name().lower() == "explorer.exe":
                break  # the Windows shell is not "us"; stop before it
            pids.add(parent.pid)  # the terminal, editor or launcher ULTRON runs in
    except Exception:
        pass
    return pids


def _console_window() -> int:
    try:
        import ctypes
        return ctypes.windll.kernel32.GetConsoleWindow()
    except Exception:
        return 0
