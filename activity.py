"""Personal activity log: what you did, kept on this PC only.

Three parts:

1. Command log. Every command ULTRON runs becomes one row in a local SQLite
   database (data/activity.db): what you said, the result, the app or git
   repo and branch involved. A write takes well under a millisecond.

2. App tracker (ACTIVITY_TRACKING, on by default; "pause tracking" stops it).
   Every 30 s (ACTIVITY_INTERVAL_SECONDS) one Win32 call reads the foreground
   app, and the time is added to that app and project ("Code", "ULTRON").
   No screenshots, no keystrokes, no AI. Window titles are read only to find
   the project name and to skip private windows; they are stored only if
   ACTIVITY_STORE_TITLES=1. Time while you are away from the keyboard
   (5 min without input) is not counted. Apps and title words in
   data/activity_settings.json "exclude" are never recorded.

3. Daily summaries. When ULTRON has been unused for a while
   (ACTIVITY_SUMMARY_IDLE_MINUTES, default 20) a background thread asks the
   LLM to condense the day into a few lines (ACTIVITY_SUMMARIES=0 turns it
   off). The LLM only ever sees profile.md plus a short summary, never the
   raw log.

Everything lives in readable local files under data/.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

from logger import logger

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("ULTRON_DATA_DIR", os.path.join(PROJECT_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "activity.db")
SETTINGS_PATH = os.path.join(DATA_DIR, "activity_settings.json")
PROFILE_PATH = os.getenv("ULTRON_PROFILE_FILE", os.path.join(PROJECT_DIR, "profile.md"))


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")


TRACKING_ENABLED = _flag("ACTIVITY_TRACKING", "1")
STORE_TITLES = _flag("ACTIVITY_STORE_TITLES", "0")
SUMMARIES_ENABLED = _flag("ACTIVITY_SUMMARIES", "1")
INTERVAL_SECONDS = float(os.getenv("ACTIVITY_INTERVAL_SECONDS", "30"))
SUMMARY_IDLE_SECONDS = float(os.getenv("ACTIVITY_SUMMARY_IDLE_MINUTES", "20")) * 60
AWAY_SECONDS = 300
PROMPT_WORD_LIMIT = 300

DEFAULT_SETTINGS = {
    "_help": "paused: stop the app tracker. exclude: app names or window-title words never recorded.",
    "paused": False,
    "exclude": ["KeePass", "1Password", "Bitwarden", "LastPass", "InPrivate", "Incognito", "Private Browsing",
                "bank", "netbanking"],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    ts REAL, day TEXT, kind TEXT, said TEXT, result TEXT, app TEXT, repo TEXT, branch TEXT);
CREATE TABLE IF NOT EXISTS app_time (
    day TEXT, app TEXT, project TEXT, seconds REAL, title TEXT,
    PRIMARY KEY (day, app, project));
CREATE TABLE IF NOT EXISTS summaries (day TEXT PRIMARY KEY, text TEXT, made_at REAL);
CREATE INDEX IF NOT EXISTS events_day ON events(day);
"""

# Friendly names for common executables.
APP_NAMES = {
    "code": "VS Code", "cursor": "Cursor", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox",
    "windowsterminal": "Terminal", "powershell": "PowerShell", "cmd": "Command Prompt",
    "explorer": "File Explorer", "pycharm64": "PyCharm", "idea64": "IntelliJ", "slack": "Slack",
    "discord": "Discord", "spotify": "Spotify", "winword": "Word", "excel": "Excel",
    "powerpnt": "PowerPoint", "outlook": "Outlook", "teams": "Teams", "ms-teams": "Teams",
    "notepad": "Notepad", "obsidian": "Obsidian", "notion": "Notion",
}
# Editors whose title is "<file> - <folder> - <editor>".
_EDITOR_TITLE = re.compile(r"(?:.* - )?(?P<project>[^-]+?) - (Visual Studio Code|Cursor)$")
_JETBRAINS_TITLE = re.compile(r"^(?P<project>[^ –-]+) [–-] ")


def today() -> str:
    return date.today().isoformat()


def classify(said: str) -> str:
    s = said.lower()
    for kind, words in (("git", ("git ", "branch", "commit", "stash")), ("open", ("open ", "launch ")),
                        ("note", ("note",)), ("timer", ("timer", "remind")), ("project", ("project",)),
                        ("type", ("type ", "write "))):
        if any(w in s for w in words):
            return kind
    return "other"


def git_repo_and_branch(start: str | None = None) -> tuple[str | None, str | None]:
    """Repo folder and branch by reading .git/HEAD (no subprocess, sub-millisecond)."""
    path = os.path.abspath(start or os.getcwd())
    while True:
        git = os.path.join(path, ".git")
        if os.path.exists(git):
            try:
                if os.path.isfile(git):  # a worktree: "gitdir: <path>"
                    with open(git, encoding="utf-8") as f:
                        git = f.read().split(":", 1)[1].strip()
                with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
                    head = f.read().strip()
                branch = head.rsplit("/", 1)[-1] if head.startswith("ref:") else head[:8]
                if head.startswith("ref: refs/heads/"):
                    branch = head[len("ref: refs/heads/"):]
                return path, branch
            except Exception:
                return path, None
        parent = os.path.dirname(path)
        if parent == path:
            return None, None
        path = parent


def project_from_title(app: str, title: str) -> str:
    m = _EDITOR_TITLE.match(title)
    if m and app in ("VS Code", "Cursor"):
        return m.group("project").strip().lstrip("● ").strip()
    m = _JETBRAINS_TITLE.match(title)
    if m and app in ("PyCharm", "IntelliJ"):
        return m.group("project")
    return ""


class ActivityLog:
    def __init__(self, db_path: str = DB_PATH, settings_path: str = SETTINGS_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.settings_path = settings_path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(SCHEMA)
        self.settings = self._load_settings()
        self.last_used = time.monotonic()
        self.busy = False

    # Settings -----------------------------------------------------------

    def _load_settings(self) -> dict:
        settings = dict(DEFAULT_SETTINGS)
        try:
            with open(self.settings_path, encoding="utf-8") as f:
                settings.update(json.load(f))
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"Could not read {self.settings_path}: {e}")
        return settings

    def save_settings(self):
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2)

    def set_paused(self, paused: bool):
        self.settings["paused"] = paused
        self.save_settings()

    def is_excluded(self, app: str, title: str) -> bool:
        text = f"{app} {title}".lower()
        return any(word.lower() in text for word in self.settings.get("exclude", []))

    # Writing ------------------------------------------------------------

    def log_command(self, said: str, result: str | None):
        kind = classify(said)
        repo = branch = None
        if kind == "git":
            repo, branch = git_repo_and_branch()
        app = None
        m = re.match(r"\s*(?:open|launch)\s+(.+?)\W*$", said, re.IGNORECASE)
        if m:
            app = m.group(1)
        with self._lock:
            self._db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
                             (time.time(), today(), kind, said, (result or "")[:300], app, repo, branch))
        self.last_used = time.monotonic()

    def add_app_time(self, app: str, project: str, seconds: float, title: str = "", day: str | None = None):
        with self._lock:
            self._db.execute(
                "INSERT INTO app_time VALUES (?,?,?,?,?) ON CONFLICT(day, app, project) "
                "DO UPDATE SET seconds = seconds + excluded.seconds, title = excluded.title",
                (day or today(), app, project, seconds, title if STORE_TITLES else ""))

    def forget_day(self, day: str | None = None):
        day = day or today()
        with self._lock:
            for table in ("events", "app_time", "summaries"):
                self._db.execute(f"DELETE FROM {table} WHERE day = ?", (day,))

    def save_summary(self, day: str, text: str):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO summaries VALUES (?,?,?)", (day, text, time.time()))

    # Reading ------------------------------------------------------------

    def app_totals(self, day: str) -> list[tuple[str, str, float]]:
        with self._lock:
            return self._db.execute("SELECT app, project, seconds FROM app_time WHERE day = ? "
                                    "ORDER BY seconds DESC", (day,)).fetchall()

    def events(self, day: str) -> list[tuple]:
        with self._lock:
            return self._db.execute("SELECT ts, kind, said, result, app, repo, branch FROM events "
                                    "WHERE day = ? ORDER BY ts", (day,)).fetchall()

    def summary(self, day: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT text FROM summaries WHERE day = ?", (day,)).fetchone()
        return row[0] if row else None

    def summary_made_at(self, day: str) -> float:
        with self._lock:
            row = self._db.execute("SELECT made_at FROM summaries WHERE day = ?", (day,)).fetchone()
        return row[0] if row else 0.0

    def last_git(self) -> tuple[str | None, str | None]:
        with self._lock:
            row = self._db.execute("SELECT repo, branch FROM events WHERE repo IS NOT NULL "
                                   "ORDER BY ts DESC LIMIT 1").fetchone()
        return (row[0], row[1]) if row else (None, None)

    def digest(self, day: str) -> str:
        """A plain, short description of a day, without the LLM."""
        totals = self.app_totals(day)
        parts = []
        for app, project, seconds in totals[:5]:
            if seconds >= 60:
                parts.append(f"{app}{' on ' + project if project else ''} for {_duration(seconds)}")
        events = self.events(day)
        kinds = {}
        for _ts, kind, *_ in events:
            kinds[kind] = kinds.get(kind, 0) + 1
        text = ""
        if parts:
            text = "Time: " + ", ".join(parts) + "."
        if events:
            branches = sorted({e[6] for e in events if e[6]})
            text += f" Commands: {len(events)}" + (f", git branches {', '.join(branches)}" if branches else "") + "."
        return text.strip()


def _duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} minutes"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hour{'s' if hours > 1 else ''}" + (f" {minutes} minutes" if minutes >= 5 else "")


# Foreground app (Windows) ------------------------------------------------

class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def seconds_since_input() -> float:
    info = _LastInput()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0


def foreground_app() -> tuple[str, str] | None:
    """(app name, window title) of the foreground window, or None."""
    import psutil

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    try:
        exe = psutil.Process(pid.value).name()
    except Exception:
        return None
    stem = os.path.splitext(exe)[0].lower()
    return APP_NAMES.get(stem, os.path.splitext(exe)[0]), buf.value


class Tracker(threading.Thread):
    """Adds INTERVAL_SECONDS to the foreground app every tick."""

    def __init__(self, log: ActivityLog, interval: float = INTERVAL_SECONDS):
        super().__init__(daemon=True, name="activity-tracker")
        self.log, self.interval = log, interval
        self.tick_ms: list[float] = []

    def tick(self):
        if self.log.settings.get("paused") or seconds_since_input() > AWAY_SECONDS:
            return
        start = time.perf_counter()
        fg = foreground_app()
        if fg:
            app, title = fg
            if not self.log.is_excluded(app, title):
                self.log.add_app_time(app, project_from_title(app, title), self.interval, title)
        self.tick_ms = (self.tick_ms + [(time.perf_counter() - start) * 1000])[-100:]

    def run(self):
        while True:
            time.sleep(self.interval)
            try:
                self.tick()
            except Exception as e:
                logger.debug(f"Activity tracker tick failed: {e}")


# Summaries ----------------------------------------------------------------

def read_profile() -> str:
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return "\n".join(line for line in f.read().splitlines() if line.strip() and not line.startswith("<!--"))
    except FileNotFoundError:
        return ""


def _limit_words(text: str, limit: int) -> str:
    words = text.split()
    return text if len(words) <= limit else " ".join(words[:limit]) + " ..."


def prompt_note(log: ActivityLog | None) -> str:
    """profile.md plus today's summary, at most about 300 words. Never the raw log."""
    parts = []
    profile = read_profile()
    if profile:
        parts.append("About the user:\n" + profile)
    if log is not None:
        day_text = log.summary(today()) or log.digest(today())
        if day_text:
            parts.append("Today so far: " + day_text)
    return _limit_words("\n".join(parts), PROMPT_WORD_LIMIT) if parts else ""


SUMMARY_PROMPT = (
    "Summarise this person's computer day in at most 4 short plain sentences for their own diary: "
    "main projects, branches, what got done, anything left open. No markdown, no advice.\n\n{digest}\n\n"
    "Commands they gave (time, what they said):\n{commands}"
)


def summarise_day(log: ActivityLog, day: str, ask) -> str | None:
    digest = log.digest(day)
    events = log.events(day)
    if not digest and not events:
        return None
    commands = "\n".join(f"{datetime.fromtimestamp(e[0]):%H:%M} {e[2][:80]}" for e in events[-40:])
    text = ask(SUMMARY_PROMPT.format(digest=digest or "(no app time recorded)", commands=commands or "(none)"))
    if text:
        log.save_summary(day, text.strip())
    return text


class Summariser(threading.Thread):
    """Writes daily summaries, only while ULTRON is idle."""

    def __init__(self, log: ActivityLog, ask, check_every: float = 60):
        super().__init__(daemon=True, name="activity-summariser")
        self.log, self.ask, self.check_every = log, ask, check_every

    def due(self, day: str) -> bool:
        if self.log.busy or time.monotonic() - self.log.last_used < SUMMARY_IDLE_SECONDS:
            return False
        made = self.log.summary_made_at(day)
        return time.time() - made > 3600 and bool(self.log.events(day) or self.log.app_totals(day))

    def run(self):
        while True:
            time.sleep(self.check_every)
            for day in ((date.today() - timedelta(days=1)).isoformat(), today()):
                try:
                    if self.due(day) and (day == today() or not self.log.summary(day)):
                        summarise_day(self.log, day, self.ask)
                        logger.info(f"Activity summary written for {day}")
                except Exception as e:
                    logger.debug(f"Activity summary failed: {e}")


_log: ActivityLog | None = None


def get_log() -> ActivityLog | None:
    global _log
    if _log is None:
        try:
            _log = ActivityLog()
        except Exception as e:
            logger.warning(f"Activity log unavailable: {e}")
    return _log


def start_background(ask):
    """Start the tracker and summariser threads (call once at startup)."""
    log = get_log()
    if log is None:
        return
    if TRACKING_ENABLED and os.name == "nt":
        Tracker(log).start()
        state = "paused" if log.settings.get("paused") else "on"
        logger.info(f"App tracker {state}: app and project names every {INTERVAL_SECONDS:.0f} s, stored in {DB_PATH}")
    if SUMMARIES_ENABLED:
        Summariser(log, ask).start()
