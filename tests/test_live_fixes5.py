"""Fixes from the live run at 20:25 on 2026-11-15 (D34). Nothing real runs: no mic, no model, no browser."""
import time
import types

import numpy as np

from ultron import app, commands, persona  # noqa: F401  (commands registers every command)
from ultron.audio import capture
from ultron.commands import router
from ultron.commands.registry import Done
from ultron.stt import whisper


# ---- 1. silence never reaches Whisper; idle conversations end ----
class _FakeStream:
    def __init__(self, loudness):
        self.loudness = loudness

    def read(self, n, exception_on_overflow=False):
        return (np.full(n, self.loudness, dtype=np.int16)).tobytes()

    def is_active(self):
        return True


def _handler(loudness):
    h = capture.AudioHandler.__new__(capture.AudioHandler)
    h.stream = _FakeStream(loudness)
    h.start_stream = lambda: True
    h.stop_stream = lambda: None
    return h


def test_record_phrase_returns_empty_when_nobody_spoke():
    audio = _handler(0).record_phrase(max_seconds=0.5)
    assert len(audio) == 0


def test_record_phrase_keeps_speech():
    audio = _handler(3000).record_phrase(max_seconds=0.5)
    assert len(audio) > 0


def test_record_phrase_with_preroll_counts_as_speech():
    pre = [np.full(1280, 3000, dtype=np.int16)]
    assert len(_handler(0).record_phrase(max_seconds=0.3, silence_timeout_seconds=0.2, preroll=pre)) > 0


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


# ---- 2. closing apps: announce only where unsaved work is possible, never both lines ----
def test_announce_only_for_apps_with_unsaved_work():
    close = router.registry.get("close_app")
    for app_name in ("notepad", "vs code", "word", "this", "microsoft excel"):
        assert router._worth_announcing(close, {"app": app_name}), app_name
    for app_name in ("chrome", "google chrome", "spotify", "discord", "calculator"):
        assert not router._worth_announcing(close, {"app": app_name}), app_name
    assert router._worth_announcing(router.registry.get("git_push"), {})


class _SpokenIO(router.Interaction):
    def announce(self, text):
        time.sleep(0.05)
        return False


def test_announced_done_reply_is_not_said_again(monkeypatch):
    cmd = router.registry.get("close_app")
    monkeypatch.setattr(router.registry, "call", lambda c, a: Done("Closed Notepad."))
    timings_before = router._announce_seconds[0]
    assert router.execute(cmd, {"app": "notepad"}, _SpokenIO()) == ""
    assert router._announce_seconds[0] > timings_before  # announce time is still measured (announce_ms)


def test_unannounced_close_says_closed(monkeypatch):
    cmd = router.registry.get("close_app")
    monkeypatch.setattr(router.registry, "call", lambda c, a: Done("Closed Chrome."))
    assert router.execute(cmd, {"app": "chrome"}, _SpokenIO()) == "Closed Chrome."


# ---- 3. Whisper: one pass by default, low confidence is logged ----
class _Seg:
    def __init__(self, text, avg_logprob=-0.2, no_speech_prob=0.01):
        self.text, self.avg_logprob, self.no_speech_prob = text, avg_logprob, no_speech_prob


def _stt(monkeypatch, segs, fallback):
    seen = {}

    class Model:
        def transcribe(self, audio, **kw):
            seen.update(kw)
            return iter(segs), None

    s = whisper.SpeechToText.__new__(whisper.SpeechToText)
    s.model, s.device = Model(), "cpu"
    monkeypatch.setattr(whisper, "WHISPER_TEMPERATURE_FALLBACK", fallback)
    return s, seen


def test_whisper_temperature_zero_by_default(monkeypatch):
    s, seen = _stt(monkeypatch, [_Seg(" open chrome")], fallback=False)
    assert s.transcribe(np.ones(16000, dtype=np.float32)) == "open chrome"
    assert seen["temperature"] == 0.0


def test_whisper_fallback_can_be_switched_on(monkeypatch):
    s, seen = _stt(monkeypatch, [_Seg("open chrome")], fallback=True)
    s.transcribe(np.ones(16000, dtype=np.float32))
    assert "temperature" not in seen  # faster-whisper's own retry ladder


def test_low_confidence_is_logged(monkeypatch):
    lines = []
    monkeypatch.setattr(whisper.logger, "info", lines.append)
    s, _ = _stt(monkeypatch, [_Seg("close google chrome", avg_logprob=-1.6)], fallback=False)
    s.transcribe(np.ones(16000, dtype=np.float32))
    assert any("Low-confidence" in line and "-1.60" in line for line in lines)
    lines.clear()
    s, _ = _stt(monkeypatch, [_Seg("open chrome")], fallback=False)
    s.transcribe(np.ones(16000, dtype=np.float32))
    assert not any("Low-confidence" in line for line in lines)


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
