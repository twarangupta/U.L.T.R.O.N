"""Voice commands for the personal activity log (see activity.py).

    "what did I work on yesterday?" / "... today?"   the day's summary
    "continue where I left off"                      reopen the last VS Code project
    "morning brief"                                  yesterday, where you stopped, what is open
    "pause tracking" / "resume tracking"             the app tracker
    "forget today"                                   delete today's activity
    "are you tracking me?"                           tracker status
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import date, timedelta
from urllib.parse import unquote, urlparse

import activity
import persona
from commands.text import normalize

_DAY_QUERY = re.compile(r"^what (did|have) i (work(ed)? on|do|done|been doing)( (yesterday|today|so far today))?$"
                        r"|^(summarise|summarize|recap) (my )?(day|yesterday|today)$")
_CONTINUE = {"continue where i left off", "pick up where i left off", "resume where i left off",
             "resume my work", "back to work", "where was i", "where did i leave off"}
_BRIEF = {"morning brief", "good morning", "brief me", "daily brief", "give me my morning brief", "my morning brief"}
_PAUSE = {"pause tracking", "stop tracking", "stop tracking me", "pause activity tracking", "pause the tracker"}
_RESUME = {"resume tracking", "start tracking", "start tracking again", "resume activity tracking"}
_FORGET_TODAY = {"forget today", "delete today", "forget today s activity", "delete today s activity",
                 "forget what i did today"}
_STATUS = {"are you tracking me", "tracking status", "what are you tracking", "is tracking on"}


def last_vscode_folder() -> str | None:
    """The folder of the last active VS Code window, from VS Code's own state file."""
    path = os.path.join(os.getenv("APPDATA", ""), "Code", "User", "globalStorage", "storage.json")
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f).get("windowsState", {})
        uri = (state.get("lastActiveWindow") or {}).get("folder")
        if not uri or not uri.startswith("file://"):
            return None
        folder = unquote(urlparse(uri).path).lstrip("/")
        return os.path.normpath(folder) if os.path.isdir(folder) else None
    except Exception:
        return None


def _open_in_vscode(folder: str):
    subprocess.Popen(["cmd", "/c", "code", folder], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _uncommitted(repo: str) -> bool:
    try:
        out = subprocess.run(["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True, timeout=5)
        return bool(out.stdout.strip())
    except Exception:
        return False


def _day_text(log, day: str) -> str | None:
    return log.summary(day) or log.digest(day) or None


def _where_i_stopped(log) -> tuple[str | None, str | None]:
    folder = last_vscode_folder()
    if folder:
        return folder, activity.git_repo_and_branch(folder)[1]
    return log.last_git()


def match_activity(text: str) -> str | None:
    n = normalize(text)
    log = activity.get_log()
    if log is None:
        return None
    if _DAY_QUERY.match(n):
        day = date.today() - timedelta(days=1) if "yesterday" in n else date.today()
        return _day_text(log, day.isoformat()) or persona.pick(persona.ACTIVITY_NOTHING)
    if n in _CONTINUE:
        folder, branch = _where_i_stopped(log)
        if not folder:
            return persona.pick(persona.ACTIVITY_NOTHING)
        _open_in_vscode(folder)
        return f"Reopening {os.path.basename(folder)}" + (f", branch {branch}." if branch else ".")
    if n in _BRIEF:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        parts = [persona.pick(persona.BRIEF_OPENERS)]
        said = _day_text(log, yesterday)
        parts.append(f"Yesterday: {said}" if said else "Nothing recorded yesterday.")
        folder, branch = _where_i_stopped(log)
        if folder:
            parts.append(f"You stopped in {os.path.basename(folder)}" + (f" on {branch}." if branch else "."))
            if _uncommitted(folder):
                parts.append("There are uncommitted changes there.")
        return " ".join(parts)
    if n in _PAUSE:
        log.set_paused(True)
        return persona.pick(persona.TRACKING_PAUSED)
    if n in _RESUME:
        log.set_paused(False)
        return persona.pick(persona.TRACKING_RESUMED)
    if n in _FORGET_TODAY:
        log.forget_day()
        return persona.pick(persona.MEMORY_FORGOT)
    if n in _STATUS:
        if not activity.TRACKING_ENABLED:
            return "The app tracker is off in settings. I only log the commands you give me."
        if log.settings.get("paused"):
            return "Tracking is paused. I only log the commands you give me."
        return ("I note which app and project is in front, every 30 seconds, plus the commands you give me. "
                "Nothing leaves this PC. Say pause tracking to stop.")
    return None
