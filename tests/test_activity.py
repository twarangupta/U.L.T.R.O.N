import pytest

pytestmark = pytest.mark.real_handlers  # handlers run against temp files set up in these tests

import os
import sys
import time


import pytest  # noqa: E402

from ultron import activity  # noqa: E402
from ultron.commands import activity_cmds  # noqa: E402


@pytest.fixture
def log(tmp_path, monkeypatch):
    lg = activity.ActivityLog(str(tmp_path / "a.db"), str(tmp_path / "s.json"))
    monkeypatch.setattr(activity, "get_log", lambda: lg)
    monkeypatch.setattr(activity, "PROFILE_PATH", str(tmp_path / "profile.md"))
    monkeypatch.setattr(activity_cmds, "last_vscode_folder", lambda: None)
    return lg


def test_command_rows_and_git_branch(log):
    log.log_command("git status", "Clean.")
    log.log_command("open chrome", "Opening Chrome.")
    rows = log.events(activity.today())
    assert [r[1] for r in rows] == ["git", "open"]
    assert rows[0][5] and rows[0][6]          # repo and branch read from .git/HEAD
    assert rows[1][4] == "chrome"


def test_write_is_fast(log):
    start = time.perf_counter()
    for _ in range(200):
        log.log_command("open chrome", "Opening Chrome.")
    assert (time.perf_counter() - start) / 200 < 0.005   # well under 5 ms even on slow disks


def test_app_time_adds_up_and_digest(log):
    for _ in range(6):
        log.add_app_time("VS Code", "ULTRON", 30)
    log.add_app_time("Chrome", "", 300)
    assert log.app_totals(activity.today())[0] == ("Chrome", "", 300)
    digest = log.digest(activity.today())
    assert "VS Code on ULTRON for 3 minutes" in digest


def test_titles_not_stored_by_default(log):
    log.add_app_time("Chrome", "", 30, title="My bank statement")
    row = log._db.execute("SELECT title FROM app_time").fetchone()
    assert row[0] == ""


def test_exclusions(log):
    assert log.is_excluded("Chrome", "New InPrivate tab")
    assert log.is_excluded("KeePass", "Database")
    assert not log.is_excluded("VS Code", "main.py - ULTRON - Visual Studio Code")


def test_project_from_title():
    assert activity.project_from_title("VS Code", "activity.py - ULTRON - Visual Studio Code") == "ULTRON"
    assert activity.project_from_title("VS Code", "â— notes.md - blog - Visual Studio Code") == "blog"
    assert activity.project_from_title("Chrome", "x - y - Google Chrome") == ""


def test_forget_today(log):
    log.log_command("git status", "ok")
    log.add_app_time("Chrome", "", 30)
    log.forget_day()
    assert log.events(activity.today()) == [] and log.app_totals(activity.today()) == []


def test_summary_uses_digest_not_raw_titles(log):
    log.add_app_time("VS Code", "ULTRON", 3600, title="secret.txt - ULTRON - Visual Studio Code")
    seen = {}

    def fake_ask(prompt):
        seen["prompt"] = prompt
        return "Worked on ULTRON for an hour."
    activity.summarise_day(log, activity.today(), fake_ask)
    assert "secret.txt" not in seen["prompt"]
    assert log.summary(activity.today()) == "Worked on ULTRON for an hour."


def test_summariser_waits_while_busy_or_recently_used(log):
    s = activity.Summariser(log, ask=lambda p: "x")
    log.log_command("git status", "ok")
    assert not s.due(activity.today())               # just used
    log.last_used -= activity.SUMMARY_IDLE_SECONDS + 1
    assert s.due(activity.today())
    log.busy = True
    assert not s.due(activity.today())


def test_prompt_note_is_short(log, tmp_path):
    (tmp_path / "profile.md").write_text("Name: Twaran\n" + "word " * 500, encoding="utf-8")
    note = activity.prompt_note(log)
    assert note.startswith("About the user") and len(note.split()) <= activity.PROMPT_WORD_LIMIT + 1


def test_voice_commands(log):
    assert "Paused" in activity_cmds.match_activity("pause tracking") or log.settings["paused"]
    assert log.settings["paused"] is True
    activity_cmds.match_activity("resume tracking")
    assert log.settings["paused"] is False
    log.save_summary(activity.today(), "Fixed the wake word.")
    assert activity_cmds.match_activity("What did I work on today?") == "Fixed the wake word."
    assert activity_cmds.match_activity("what did i work on yesterday") is not None
    assert activity_cmds.match_activity("morning brief").count(".") >= 1
    assert activity_cmds.match_activity("open chrome") is None
