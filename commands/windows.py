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

from commands.text import normalize

# Spoken name -> process names (lowercase, without .exe)
APP_ALIASES: dict[str, tuple[str, ...]] = {
    "chrome": ("chrome",), "google chrome": ("chrome",), "google": ("chrome",),
    "edge": ("msedge",), "microsoft edge": ("msedge",),
    "firefox": ("firefox",), "brave": ("brave",), "opera": ("opera",),
    "vs code": ("code",), "vscode": ("code",), "visual studio code": ("code",), "code": ("code",),
    "visual studio": ("devenv",),
    "notepad": ("notepad",), "notepad plus plus": ("notepad++",),
    "file explorer": ("explorer",), "explorer": ("explorer",), "files": ("explorer",),
    "word": ("winword",), "excel": ("excel",), "powerpoint": ("powerpnt",), "outlook": ("outlook", "olk"),
    "teams": ("ms-teams", "teams"), "spotify": ("spotify",), "discord": ("discord",),
    "whatsapp": ("whatsapp",), "telegram": ("telegram",), "zoom": ("zoom",), "slack": ("slack",),
    "vlc": ("vlc",), "steam": ("steam",), "obs": ("obs64", "obs"),
    "terminal": ("windowsterminal",), "task manager": ("taskmgr",), "settings": ("systemsettings",),
    "calculator": ("calculatorapp", "calculator"), "paint": ("mspaint",),
    "postman": ("postman",), "figma": ("figma",), "notion": ("notion",), "obsidian": ("obsidian",),
    "pycharm": ("pycharm64",), "intellij": ("idea64",), "android studio": ("studio64",),
}
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
_THIS = {"it", "this", "that", "this window", "the window", "window", "current window", "this app"}
_EVERYTHING = {"everything", "all", "all windows", "all apps", "every window", "all the windows"}
_TRAILING_NOUNS = r"(?: app| application| window| windows| browser)?"

_CLOSE = re.compile(rf"^(?:close|quit|exit|kill) (?:the |my )?(?P<app>.+?){_TRAILING_NOUNS}$")
_MINIMISE = re.compile(
    rf"^(?:minimi[sz]e|hide) (?:the |my )?(?P<app>.+?){_TRAILING_NOUNS}"
    rf"(?: (?:except|but|other than) (?:the |my )?(?P<keep>.+?){_TRAILING_NOUNS})?$"
)
_MAXIMISE = re.compile(rf"^(?:maximi[sz]e|full ?screen) (?:the |my )?(?P<app>.+?){_TRAILING_NOUNS}$")
_SWITCH = re.compile(rf"^(?:switch to|go to|bring up|show me|focus(?: on)?) (?:the |my )?(?P<app>.+?){_TRAILING_NOUNS}$")
_RESTORE = re.compile(r"^(?:restore|bring back|unminimi[sz]e|show) (?:all )?(?:my |the )?(?:windows|everything)$")
_SHOW_DESKTOP = re.compile(r"^(?:show|go to) (?:the )?desktop$")


@dataclass
class Window:
    hwnd: int
    title: str
    process: str  # lowercase, without .exe
    pid: int


def parse(text: str) -> tuple[str, str | None, str | None] | None:
    """Return (action, app, keep) for a window command, or None."""
    norm = normalize(text)
    if _RESTORE.match(norm):
        return ("restore", None, None)
    if _SHOW_DESKTOP.match(norm):
        return ("minimise", "everything", None)
    for action, pattern in (("close", _CLOSE), ("minimise", _MINIMISE),
                            ("maximise", _MAXIMISE), ("switch", _SWITCH)):
        m = pattern.match(norm)
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


def pretty(app: str) -> str:
    return " ".join(w.upper() if w in {"vs", "vlc", "obs"} else w.capitalize() for w in app.split())


def handle(text: str, windows_api=None) -> str | None:
    """Run a window command; None if the text is not one. windows_api is for tests."""
    parsed = parse(text)
    if parsed is None:
        return None
    if sys.platform != "win32" and windows_api is None:
        return "Window control only works on Windows."
    api = windows_api or _Win32()
    action, app, keep = parsed

    if action == "restore":
        api.restore_all()
        return "Windows restored."
    if action == "minimise" and app in _EVERYTHING:
        if keep:
            kept = [w for w in api.windows() if matches(w, keep)]
            if not kept:
                return f"{pretty(keep)} isn't open."
            for w in api.windows():
                if not matches(w, keep):
                    api.minimise(w)
            return f"Everything minimised except {pretty(keep)}."
        api.minimise_all()
        return "Everything minimised."

    if app in _THIS:
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
        return f"Closed {name}."
    if action == "minimise":
        for w in targets:
            api.minimise(w)
        return f"{name} minimised."
    if action == "maximise":
        api.maximise(targets[0])
        return f"{name} maximised."
    api.focus(targets[0])
    return f"Switched to {name}."


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
