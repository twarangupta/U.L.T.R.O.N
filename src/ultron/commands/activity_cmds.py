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
import subprocess
from datetime import date, timedelta
from urllib.parse import unquote, urlparse

from ultron import activity
from ultron import persona
from ultron.commands.registry import Param, command


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


_GROUP = "Activity log"


def _log_or_none():
    return activity.get_log()


@command("day_summary", "Summarise what the user worked on today or yesterday, from the activity log.",
         params=[Param("day", "choice", "which day", required=False, choices=("today", "yesterday"))],
         group=_GROUP, title="summarise {day}", priority=72,
         rules=[r"what (?:did|have) i (?:work(?:ed)? on|do|done|been doing)(?: (?P<day>yesterday|today)| so far today)?",
                r"(?:summarise|summarize|recap) (?:my )?(?:day|(?P<day>yesterday|today))"],
         examples=["what did i work on yesterday", "what did i do today", "recap my day",
                   "summarise yesterday", "what have i been doing today", "how did i spend yesterday",
                   "what was i working on yesterday"],
         not_examples=["what did i say", "what did i eat yesterday", "what should i do today"])
def day_summary(day: str = "today") -> str | None:
    log = _log_or_none()
    if log is None:
        return "The activity log is off."
    when = date.today() - timedelta(days=1) if day == "yesterday" else date.today()
    return _day_text(log, when.isoformat()) or persona.pick(persona.ACTIVITY_NOTHING)


@command("continue_work", "Reopen the last VS Code project the user worked in.", group=_GROUP,
         title="continue where you left off", priority=72,
         rules=["(?:continue|pick up|resume) where i left off|resume my work|back to work|where was i"
                "|where did i leave off"],
         examples=["continue where i left off", "pick up where i left off", "where was i",
                   "resume my work", "take me back to what i was doing", "open my last project"])
def continue_work() -> str:
    log = _log_or_none()
    folder, branch = _where_i_stopped(log) if log else (last_vscode_folder(), None)
    if not folder:
        return persona.pick(persona.ACTIVITY_NOTHING)
    _open_in_vscode(folder)
    return f"Reopening {os.path.basename(folder)}" + (f", branch {branch}." if branch else ".")


@command("morning_brief", "Brief the user: yesterday's work, where they stopped, uncommitted changes.",
         group=_GROUP, title="morning brief", priority=72,
         rules=["(?:give me )?(?:my )?(?:morning|daily) brief(?:ing)?|good morning|brief me"],
         examples=["morning brief", "good morning", "brief me", "daily brief", "give me my morning briefing",
                   "catch me up on yesterday"])
def morning_brief() -> str:
    log = _log_or_none()
    if log is None:
        return "The activity log is off."
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


@command("pause_tracking", "Pause the app tracker (commands are still logged).", group=_GROUP,
         title="pause tracking", priority=72,
         rules=["(?:pause|stop) (?:activity )?tracking(?: me)?|pause the tracker"],
         examples=["pause tracking", "stop tracking me", "pause the tracker", "stop watching what i do",
                   "turn off activity tracking"])
def pause_tracking() -> str:
    log = _log_or_none()
    if log is None:
        return "The activity log is off."
    log.set_paused(True)
    return persona.pick(persona.TRACKING_PAUSED)


@command("resume_tracking", "Resume the app tracker.", group=_GROUP, title="resume tracking", priority=72,
         rules=["(?:resume|start) (?:activity )?tracking(?: again)?"],
         examples=["resume tracking", "start tracking again", "turn activity tracking back on",
                   "you can track me again"])
def resume_tracking() -> str:
    log = _log_or_none()
    if log is None:
        return "The activity log is off."
    log.set_paused(False)
    return persona.pick(persona.TRACKING_RESUMED)


@command("forget_today", "Delete today's activity log.", group=_GROUP, title="forget today", priority=72,
         rules=["(?:forget|delete) today(?: s activity)?|forget what i did today"],
         examples=["forget today", "delete today's activity", "forget what i did today",
                   "erase today's log"])
def forget_today() -> str:
    log = _log_or_none()
    if log is None:
        return "The activity log is off."
    log.forget_day()
    return persona.pick(persona.MEMORY_FORGOT)


@command("tracking_status", "Say whether and what the activity tracker records.", group=_GROUP,
         title="tracking status", priority=72,
         rules=["are you tracking me|tracking status|what are you tracking|is tracking on"],
         examples=["are you tracking me", "tracking status", "what are you tracking", "is tracking on",
                   "are you watching me", "what do you record about me"])
def tracking_status() -> str:
    log = _log_or_none()
    if not activity.TRACKING_ENABLED or log is None:
        return "The app tracker is off in settings. I only log the commands you give me."
    if log.settings.get("paused"):
        return "Tracking is paused. I only log the commands you give me."
    return ("I note which app and project is in front, every 30 seconds, plus the commands you give me. "
            "Nothing leaves this PC. Say pause tracking to stop.")


def match_activity(text: str) -> str | None:
    """Rules-only check of the activity commands (kept for tests and old callers)."""
    if activity.get_log() is None:
        return None
    from ultron.commands.router import run_rules
    return run_rules(text, group=_GROUP)
