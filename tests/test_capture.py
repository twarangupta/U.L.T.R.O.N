"""The shared mic (ring buffer) and the voice activity detector. No real device: a fake mic thread
pushes synthetic blocks, so nothing is recorded or played. Silero tests skip without models/silero_vad.onnx."""
import threading
import time
import types

import numpy as np
import pytest

from ultron.audio import capture, vad as vad_module
from ultron.audio.bargein import BargeInDetector
from ultron.config import CHUNK_SIZE

SPEECH, QUIET = 3000, 0


def block(level: int) -> np.ndarray:
    return np.full(CHUNK_SIZE, level, dtype=np.int16)


class ScriptVad:
    """Stands in for Silero: a block with any sound is speech. Counts how often it is asked."""
    name = "silero"

    def __init__(self):
        self.calls = 0
        self.resets = 0

    def probability(self, b):
        self.calls += 1
        return 0.9 if np.max(b) > 0 else 0.05

    def reset(self):
        self.resets += 1


class FakeMic:
    """Plays the role of the sounddevice stream: after open, a thread pushes the scripted blocks into
    the handler's ring buffer (a few ahead of the reader), then silence."""

    def __init__(self, handler, script):
        self.handler, self.script, self.opens = handler, list(script), 0
        self.active = True
        self._stop = threading.Event()

    def open(self):
        self.opens += 1
        threading.Thread(target=self._feed, daemon=True).start()
        return self

    def _feed(self):
        i = 0
        while not self._stop.is_set():
            if len(self.handler._blocks) >= 3:
                time.sleep(0.0005)
                continue
            self.handler.push(self.script[i] if i < len(self.script) else block(QUIET))
            i += 1

    def stop(self):
        self._stop.set()
        self.active = False

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _no_keyboard(monkeypatch):
    monkeypatch.setattr(capture, "check_keyboard_hit", lambda: False)


def handler_with(script, vad=None):
    h = capture.AudioHandler(vad=vad or ScriptVad())
    mic = FakeMic(h, script)
    h._open_stream = mic.open
    return h, mic


# ---- lazy: importing the module opens no device ----
def test_import_opens_nothing():
    assert capture.audio_handler._stream is None


# ---- the ring buffer ----
def opened(h):
    h._stream = types.SimpleNamespace(active=True)   # pretend the mic is already open
    return h


def test_blocks_come_out_in_order():
    h = opened(capture.AudioHandler())
    for n in (1, 2, 3):
        h.push(block(n))
    assert [int(h.read_chunk()[0]) for _ in range(3)] == [1, 2, 3]


def test_full_ring_drops_the_oldest_blocks():
    h = opened(capture.AudioHandler())
    for n in range(capture.RING_BLOCKS + 5):
        h.push(block(n % 30000))
    assert len(h._blocks) == capture.RING_BLOCKS
    assert int(h.read_chunk()[0]) == 5


def test_start_stream_drops_audio_that_piled_up():
    h, mic = handler_with([])
    h.push(block(7))
    assert h.start_stream()
    assert len(h._blocks) == 0 or int(h._blocks[0][0]) == 0   # the stale 7 is gone


def test_a_stalled_device_gives_zeros_not_a_hang(monkeypatch):
    monkeypatch.setattr(capture, "READ_TIMEOUT", 0.05)
    h = capture.AudioHandler()
    h._open_stream = lambda: types.SimpleNamespace(active=True, stop=lambda: None, close=lambda: None)
    out = h.read_chunk()
    assert out.shape == (CHUNK_SIZE,) and not out.any()


def test_failed_open_reports_false():
    h = capture.AudioHandler()

    def boom():
        raise OSError("no mic")
    h._open_stream = boom
    assert h.start_stream() is False


def test_one_open_for_every_mode_switch():
    """Wake word, recording and barge-in listening are just readers: the device opens once."""
    h, mic = handler_with([block(SPEECH)] * 5)
    for _ in range(3):
        assert h.start_stream()      # wake-word mode, barge-in mode ...
        h.read_chunk()
        h.stop_stream()              # ... and the switch between them
    h.record_phrase(max_seconds=0.5)
    assert mic.opens == 1
    h.terminate()


def test_reopens_when_the_device_dies():
    h, mic = handler_with([])
    h.start_stream()
    mic.stop()                       # the device went away
    h.start_stream()
    assert mic.opens == 2


# ---- the recorder ----
def test_nobody_spoke_returns_empty():
    h, _ = handler_with([block(QUIET)] * 40)
    assert len(h.record_phrase(max_seconds=1.0)) == 0


def test_phrase_ends_after_the_vad_pause_and_keeps_a_little_lead():
    script = [block(QUIET)] * 10 + [block(SPEECH)] * 10
    h, _ = handler_with(script)
    audio = h.record_phrase(max_seconds=5.0)
    # 6 lead blocks + 10 speech + 4 pause blocks (0.35 s rounds to 4 x 80 ms)
    assert len(audio) == (capture.LEAD_BLOCKS + 10 + 4) * CHUNK_SIZE
    assert audio.dtype == np.float32 and abs(float(audio.max()) - SPEECH / 32768) < 1e-6
    assert h.last_end_silence == 0.35


def test_a_short_pause_inside_a_sentence_does_not_end_it():
    script = [block(SPEECH)] * 4 + [block(QUIET)] * 2 + [block(SPEECH)] * 4
    h, _ = handler_with(script)
    audio = h.record_phrase(max_seconds=5.0)
    assert len(audio) == (4 + 2 + 4 + 4) * CHUNK_SIZE


def test_explicit_pause_length_is_used():
    h, _ = handler_with([block(SPEECH)] * 3)
    audio = h.record_phrase(silence_timeout_seconds=0.16, max_seconds=5.0)
    assert len(audio) == (3 + 2) * CHUNK_SIZE and h.last_end_silence == 0.16


def test_recording_stops_at_max_seconds():
    h, _ = handler_with([block(SPEECH)] * 100)
    assert len(h.record_phrase(max_seconds=0.4)) == 5 * CHUNK_SIZE


def test_preroll_counts_as_speech_and_is_kept():
    pre = [block(SPEECH)]
    h, _ = handler_with([block(QUIET)] * 20)
    audio = h.record_phrase(max_seconds=2.0, preroll=pre)
    assert len(audio) == (1 + 4) * CHUNK_SIZE


def test_loudness_fallback_uses_the_old_pause():
    h, _ = handler_with([block(SPEECH)] * 3, vad=vad_module.LoudnessVad())
    audio = h.record_phrase(max_seconds=5.0)
    assert len(audio) == (3 + 8) * CHUNK_SIZE      # 0.6 s = 8 blocks
    assert h.last_end_silence == capture.END_SILENCE_SECONDS


def test_vad_is_reset_for_every_phrase():
    vad = ScriptVad()
    h, _ = handler_with([block(SPEECH)] * 2, vad=vad)
    h.record_phrase(max_seconds=1.0)
    h.record_phrase(max_seconds=0.2)
    assert vad.resets == 2


# ---- the loudness fallback and the downloader ----
def test_loudness_vad():
    v = vad_module.LoudnessVad()
    assert v.probability(block(100)) == 0.0 and v.probability(block(900)) == 1.0
    assert v.probability(np.zeros(0, dtype=np.int16)) == 0.0


def test_make_vad_falls_back_when_the_model_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(vad_module, "MODEL_PATH", str(tmp_path / "none.onnx"))
    assert vad_module.make_vad(download=False).name == "loudness"
    monkeypatch.setattr(vad_module, "download_model", lambda log=print: False)
    assert vad_module.make_vad().name == "loudness"


def test_make_vad_needs_16khz():
    assert vad_module.make_vad(sample_rate=44100).name == "loudness"


def test_download_says_what_and_shows_progress(monkeypatch, tmp_path):
    target = tmp_path / "silero_vad.onnx"
    monkeypatch.setattr(vad_module, "MODEL_PATH", str(target))
    monkeypatch.setattr(vad_module.paths, "MODELS_DIR", str(tmp_path))
    payload = b"x" * 400_000

    class Response:
        headers = {"Content-Length": str(len(payload))}

        def __init__(self):
            self.pos = 0

        def read(self, n):
            part, self.pos = payload[self.pos:self.pos + n], self.pos + n
            return part

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(vad_module.urllib.request, "urlopen", lambda url, timeout=0: Response())
    lines = []
    assert vad_module.download_model(log=lines.append) is True
    assert target.read_bytes() == payload and not (tmp_path / "silero_vad.onnx.part").exists()
    assert "Silero VAD" in lines[0] and "MB" in lines[0] and any("100%" in line for line in lines)
    assert vad_module.download_model(log=lines.append) is True   # already there: silent


def test_failed_download_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setattr(vad_module, "MODEL_PATH", str(tmp_path / "silero_vad.onnx"))
    monkeypatch.setattr(vad_module.paths, "MODELS_DIR", str(tmp_path))

    def offline(url, timeout=0):
        raise OSError("offline")
    monkeypatch.setattr(vad_module.urllib.request, "urlopen", offline)
    assert vad_module.download_model(log=lambda m: None) is False
    assert list(tmp_path.iterdir()) == []


# ---- barge-in with a voice detector ----
def loud_chunk():
    return block(2000)


def test_loud_noise_without_speech_does_not_interrupt():
    class NoSpeech(ScriptVad):
        def probability(self, b):
            self.calls += 1
            return 0.1
    vad = NoSpeech()
    det = BargeInDetector(vad=vad, needed=3)
    assert not any(det.feed(loud_chunk()) for _ in range(20))
    assert vad.calls == 20            # asked for every chunk, so its memory stays current


def test_loud_speech_interrupts():
    det = BargeInDetector(vad=ScriptVad(), needed=3)
    results = [det.feed(block(QUIET)) for _ in range(8)] + [det.feed(loud_chunk()) for _ in range(3)]
    assert results[-1] is True and not any(results[:-1])


def test_barge_in_without_vad_is_unchanged():
    det = BargeInDetector(needed=3)
    results = [det.feed(block(QUIET)) for _ in range(8)] + [det.feed(loud_chunk()) for _ in range(3)]
    assert results[-1] is True


# ---- Silero itself (needs models/silero_vad.onnx) ----
needs_silero = pytest.mark.skipif(not vad_module.model_available(), reason="Silero VAD model not downloaded")


@needs_silero
def test_silero_hears_no_speech_in_silence_or_noise():
    v = vad_module.SileroVad()
    rng = np.random.default_rng(0)
    for _ in range(25):
        assert v.probability(np.zeros(CHUNK_SIZE, dtype=np.int16)) < 0.2
    for _ in range(25):
        assert v.probability((rng.normal(0, 600, CHUNK_SIZE)).astype(np.int16)) < 0.5


@needs_silero
def test_silero_keeps_leftover_samples_between_blocks():
    v = vad_module.SileroVad()
    v.probability(block(QUIET))
    assert len(v._pending) == CHUNK_SIZE % vad_module.WINDOW     # 1280 = 2 x 512 + 256
    v.probability(block(QUIET))
    assert len(v._pending) == (2 * CHUNK_SIZE) % vad_module.WINDOW
    v.reset()
    assert len(v._pending) == 0


@needs_silero
def test_silero_is_repeatable_after_reset():
    rng = np.random.default_rng(1)
    blocks = [(rng.normal(0, 3000, CHUNK_SIZE)).astype(np.int16) for _ in range(6)]
    v = vad_module.SileroVad()
    first = [v.probability(b) for b in blocks]
    v.reset()
    assert [v.probability(b) for b in blocks] == first


@needs_silero
def test_two_detectors_do_not_share_memory():
    a, b = vad_module.SileroVad(), vad_module.SileroVad()
    rng = np.random.default_rng(2)
    noise = [(rng.normal(0, 3000, CHUNK_SIZE)).astype(np.int16) for _ in range(5)]
    solo = [b.probability(x) for x in noise]
    b.reset()
    for x in noise:
        a.probability(x)             # a runs between b's calls
        b.probability(x)
    b.reset()
    assert [b.probability(x) for x in noise] == solo

