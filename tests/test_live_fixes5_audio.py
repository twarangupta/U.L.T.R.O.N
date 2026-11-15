"""Fixes from the live run at 20:25 on 2026-11-15 (D34) that need app.py.
Nothing real runs: no mic, no model. Skipped where Piper is not installed (CI): voice/speaker.py
loads the voice at import (the known caveat in CLAUDE.md). The mic tests moved to test_capture.py,
which runs everywhere since audio/capture.py opens nothing at import."""
import types

import numpy as np
import pytest

pytest.importorskip("piper")

from ultron import app, persona  # noqa: E402

# ---- 1. silence never reaches Whisper (the recorder side is in test_capture.py); idle conversations end ----
def test_transcribe_skips_empty_audio():
    class Boom:
        def transcribe(self, audio):
            raise AssertionError("Whisper must not hear silence")
    assert app.transcribe(Boom(), np.zeros(0, dtype=np.float32)) == ""


def test_idle_expiry():
    assert not app.idle_expired(100.0, 120.0, limit=45)
    assert app.idle_expired(100.0, 145.0, limit=45)
    assert not app.idle_expired(0.0, 1e6, limit=0)  # 0 turns it off


def test_idle_line_is_original_persona_and_prerendered():
    assert persona.IDLE_REPLIES and all(line in persona.fixed_lines() for line in persona.IDLE_REPLIES)

# ---- 5. a starting browser must not starve the voice: ULTRON runs at above-normal priority ----
def test_priority_boost_calls_windows_once(monkeypatch):
    calls = []
    fake_kernel = types.SimpleNamespace(
        GetCurrentProcess=lambda: 123, SetPriorityClass=lambda h, c: calls.append((h, c)) or 1)
    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app, "_kernel32", lambda: fake_kernel)
    assert app.raise_priority() is True
    assert calls == [(123, app.ABOVE_NORMAL_PRIORITY_CLASS)]


def test_priority_boost_is_a_noop_elsewhere(monkeypatch):
    monkeypatch.setattr(app.sys, "platform", "linux")
    assert app.raise_priority() is False


def test_priority_boost_failure_is_not_fatal(monkeypatch):
    fake_kernel = types.SimpleNamespace(GetCurrentProcess=lambda: 1, SetPriorityClass=lambda h, c: 0)
    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app, "_kernel32", lambda: fake_kernel)
    assert app.raise_priority() is False
