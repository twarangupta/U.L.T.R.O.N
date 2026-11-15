"""Fixes from the live run at 20:25 on 2026-11-15 (D34): close announce and Whisper settings.
Nothing real runs: no mic, no model, no browser. The app and mic parts are in test_live_fixes5_audio.py."""
import time

import numpy as np

from ultron import commands  # noqa: F401  (commands registers every command)
from ultron.commands import router
from ultron.commands.registry import Done
from ultron.stt import whisper

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
