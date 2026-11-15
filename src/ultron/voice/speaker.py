"""ULTRON's voice: Piper TTS, streamed sentence by sentence to one open output.

Why it is built this way:
- Playback starts as soon as the first sentence is synthesized, instead of
  after the whole reply (that was the 2 to 3 second gap).
- One output stream stays open for the whole session; opening a new one per
  reply adds delay.
- Short lines are cached, and the fixed persona lines are pre-rendered at
  startup, so "Yes?", "Done." and friends play instantly.
- The printed text appears when the voice starts, not before.
- Every speak() or stop() bumps a generation number. Audio from an older
  generation is dropped, so stopping never waits for synthesis to finish.
- Synthesis runs ahead of playback: one thread turns text into audio, sentence
  by sentence, into a small queue, while another plays it. So the next
  sentence is ready when the current one ends (it used to be synthesized only
  after the current one finished playing, a 0.3 to 1 s gap at every full stop).
- Each sentence's own leading and trailing silence is trimmed and a fixed
  pause (VOICE_SENTENCE_PAUSE, 0.13 s) is added, so pauses sound even.
"""
import os
import queue
import threading
import time

import numpy as np
import sounddevice as sd
from piper import PiperVoice
from piper.config import SynthesisConfig

from ultron import paths
from ultron.config import VOICE_SPEED
from ultron.logger import logger
from ultron.voice.tts_text import prepare_for_speech

MODEL_PATHS = [
    os.getenv("VOICE_MODEL_PATH", os.path.join(paths.MODELS_DIR, "ultron-voice.onnx")),
    os.path.join(paths.MODELS_DIR, "jarvis-high.onnx"),  # name used by older installs
]
BLOCK_SAMPLES = 1024           # about 46 ms at 22 kHz; stop reacts within one block
CACHE_MAX_CHARS = 120          # only short, repeated lines are worth caching
CACHE_MAX_ITEMS = 300
SENTENCE_PAUSE_SECONDS = float(os.getenv("VOICE_SENTENCE_PAUSE", "0.13"))
SILENCE_LEVEL = 300            # int16 samples quieter than this at the edges count as silence
AHEAD_SENTENCES = 6            # how many synthesized sentences may wait for playback


def trim_and_pause(pcm: np.ndarray, rate: int, pause_seconds: float = SENTENCE_PAUSE_SECONDS) -> np.ndarray:
    """Cut near-silence from both ends (keeping 20 ms) and append a fixed pause."""
    loud = np.flatnonzero(np.abs(pcm.astype(np.int32)) > SILENCE_LEVEL)
    margin = int(0.02 * rate)
    if len(loud):
        pcm = pcm[max(loud[0] - margin, 0):loud[-1] + margin + 1]
    return np.concatenate([pcm, np.zeros(int(pause_seconds * rate), dtype=np.int16)])


class Speaker:
    def __init__(self):
        self.voice = None
        self._queue: queue.Queue[tuple[int, str]] = queue.Queue()
        self._generation = 0
        self._idle = threading.Event()
        self._idle.set()
        self._state_lock = threading.Lock()   # keeps "idle", queue and generation in step
        self._synth_lock = threading.Lock()   # the phonemizer is not thread-safe
        self._cache: dict[str, np.ndarray] = {}
        # (generation, text, pcm or None at the end of a text, first piece of that text?)
        self._audio: queue.Queue = queue.Queue(maxsize=AHEAD_SENTENCES)
        self._pending = 0                     # texts queued but not finished playing
        self.first_sound_at: float | None = None  # perf_counter of the first audio since the last speak()

        path = next((p for p in MODEL_PATHS if os.path.exists(p)), None)
        if path is None:
            logger.error("Voice model not found. Run 'python download_voice.py' first.")
            return
        try:
            logger.info("Loading ULTRON voice model...")
            self.voice = PiperVoice.load(path)
            self.syn_config = SynthesisConfig(length_scale=1.0 / VOICE_SPEED)
            self.stream = sd.OutputStream(
                samplerate=self.voice.config.sample_rate, channels=1, dtype="int16", latency="low"
            )
            self.stream.start()
            threading.Thread(target=self._worker, daemon=True, name="speaker-synth").start()
            threading.Thread(target=self._player, daemon=True, name="speaker-play").start()
            logger.info("ULTRON voice loaded.")
        except Exception as e:
            logger.error(f"Error loading ULTRON voice: {e}")
            self.voice = None

    # Public API -----------------------------------------------------------

    def speak(self, text: str, append: bool = False):
        """Start speaking in the background.

        Normally stops anything already playing. With append=True the text is
        queued after what is playing (used to stream an LLM reply sentence by
        sentence).
        """
        if not append:
            self.stop()
            self.first_sound_at = None
        if not self.voice:
            print(f"\n[ULTRON]: {text}\n")
            return
        with self._state_lock:
            self._idle.clear()
            self._pending += 1
            self._queue.put((self._generation, text))

    def stop(self):
        """Stop playback now and drop anything queued. Returns immediately."""
        with self._state_lock:
            self._generation += 1
            self._pending = 0
            for q in (self._queue, self._audio):
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break
            self._idle.set()

    def wait(self):
        """Block until everything queued has been spoken."""
        self._idle.wait()

    def is_speaking(self) -> bool:
        return not self._idle.is_set()

    def prewarm(self, lines: list[str]):
        """Render fixed lines into the cache in the background."""
        if self.voice:
            threading.Thread(target=lambda: [self._render(l) for l in lines], daemon=True).start()

    # Internals ------------------------------------------------------------

    def _cancelled(self, generation: int) -> bool:
        return generation != self._generation

    def _worker(self):
        """Synthesis thread: text in, audio sentences out, running ahead of playback."""
        while True:
            generation, text = self._queue.get()
            first = True
            try:
                for pcm in self._sentences(generation, text):
                    if self._cancelled(generation):
                        break
                    self._audio.put((generation, text, pcm, first))
                    first = False
            except Exception as e:
                logger.error(f"TTS error: {e}")
            self._audio.put((generation, text, None, False))  # end of this text

    def _player(self):
        """Playback thread: writes audio continuously, in order."""
        while True:
            generation, text, pcm, first = self._audio.get()
            if self._cancelled(generation):
                continue
            if pcm is None:
                with self._state_lock:
                    if not self._cancelled(generation):
                        self._pending = max(self._pending - 1, 0)
                        if self._pending == 0:
                            self._idle.set()
                continue
            if first:
                if self.first_sound_at is None:
                    self.first_sound_at = time.perf_counter()
                print(f"\n[ULTRON]: {text}\n")
            try:
                self._play(generation, pcm)
            except Exception as e:
                logger.error(f"Audio output error: {e}")

    def _sentences(self, generation: int, text: str):
        """Yield audio sentence by sentence; whole short lines come from the cache."""
        spoken = prepare_for_speech(text)
        cached = self._cache.get(spoken)
        if cached is not None:
            yield cached
            return
        parts = []
        with self._synth_lock:
            for chunk in self.voice.synthesize(spoken, self.syn_config):
                if self._cancelled(generation):
                    return
                pcm = trim_and_pause(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16),
                                     self.voice.config.sample_rate)
                parts.append(pcm)
                yield pcm
        self._remember(spoken, parts)

    def _render(self, text: str):
        spoken = prepare_for_speech(text)
        if spoken in self._cache:
            return
        with self._synth_lock:
            parts = [trim_and_pause(np.frombuffer(c.audio_int16_bytes, dtype=np.int16),
                                    self.voice.config.sample_rate)
                     for c in self.voice.synthesize(spoken, self.syn_config)]
        self._remember(spoken, parts)

    def _remember(self, spoken: str, parts: list[np.ndarray]):
        if parts and len(spoken) <= CACHE_MAX_CHARS and len(self._cache) < CACHE_MAX_ITEMS:
            self._cache[spoken] = np.concatenate(parts)

    def _play(self, generation: int, pcm: np.ndarray):
        for start in range(0, len(pcm), BLOCK_SAMPLES):
            if self._cancelled(generation):
                return
            self.stream.write(pcm[start:start + BLOCK_SAMPLES].reshape(-1, 1))


_speaker = Speaker()


def speak(text: str, append: bool = False):
    _speaker.speak(text, append)


def first_sound_at() -> float | None:
    return _speaker.first_sound_at


def stop_speaking():
    _speaker.stop()


def wait_speaking():
    _speaker.wait()


def is_speaking() -> bool:
    return _speaker.is_speaking()


def prewarm(lines: list[str]):
    _speaker.prewarm(lines)
