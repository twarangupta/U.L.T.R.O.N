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
"""
import os
import queue
import threading

import numpy as np
import sounddevice as sd
from piper import PiperVoice
from piper.config import SynthesisConfig

from config import VOICE_SPEED
from logger import logger
from tts_text import prepare_for_speech

MODEL_PATHS = [
    os.getenv("VOICE_MODEL_PATH", "models/ultron-voice.onnx"),
    "models/jarvis-high.onnx",  # name used by older installs
]
BLOCK_SAMPLES = 1024           # about 46 ms at 22 kHz; stop reacts within one block
CACHE_MAX_CHARS = 120          # only short, repeated lines are worth caching
CACHE_MAX_ITEMS = 300


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
            threading.Thread(target=self._worker, daemon=True, name="speaker").start()
            logger.info("ULTRON voice loaded.")
        except Exception as e:
            logger.error(f"Error loading ULTRON voice: {e}")
            self.voice = None

    # Public API -----------------------------------------------------------

    def speak(self, text: str):
        """Start speaking in the background. Stops anything already playing."""
        self.stop()
        if not self.voice:
            print(f"\n[ULTRON]: {text}\n")
            return
        with self._state_lock:
            self._idle.clear()
            self._queue.put((self._generation, text))

    def stop(self):
        """Stop playback now and drop anything queued. Returns immediately."""
        with self._state_lock:
            self._generation += 1
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

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
        while True:
            generation, text = self._queue.get()
            try:
                self._say(generation, text)
            except Exception as e:
                logger.error(f"TTS error: {e}")
            finally:
                with self._state_lock:
                    if self._queue.empty():
                        self._idle.set()

    def _say(self, generation: int, text: str):
        printed = False
        for pcm in self._sentences(generation, text):
            if self._cancelled(generation):
                return
            if not printed:
                print(f"\n[ULTRON]: {text}\n")
                printed = True
            self._play(generation, pcm)

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
                pcm = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                parts.append(pcm)
                yield pcm
        self._remember(spoken, parts)

    def _render(self, text: str):
        spoken = prepare_for_speech(text)
        if spoken in self._cache:
            return
        with self._synth_lock:
            parts = [np.frombuffer(c.audio_int16_bytes, dtype=np.int16)
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


def speak(text: str):
    _speaker.speak(text)


def stop_speaking():
    _speaker.stop()


def wait_speaking():
    _speaker.wait()


def is_speaking() -> bool:
    return _speaker.is_speaking()


def prewarm(lines: list[str]):
    _speaker.prewarm(lines)
