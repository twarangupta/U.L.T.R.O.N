"""Interrupt ULTRON by talking over it (barge-in).

While ULTRON speaks, the mic also hears ULTRON's own voice from the
speakers (echo). So "any sound" cannot mean "the user is talking". Instead
this keeps a running baseline of how loud the mic is while ULTRON talks,
and only treats it as the user when the mic gets several times louder than
that baseline for about a third of a second. A person speaking at the laptop
is much louder at the mic than the echo is.

The chunks from just before and during the interruption are kept, so what
the user said is not lost: they become the start of the next recording.

Tuning (.env): BARGE_IN=0 turns it off. BARGE_IN_FACTOR (default 3.0) is how
many times louder than the echo the user must be; raise it if ULTRON stops
itself, lower it if it ignores you. With headphones there is no echo, so it
reacts to your voice almost at once.
"""
from collections import deque

import numpy as np

from ultron.config import BARGE_IN_CHUNKS, BARGE_IN_FACTOR, BARGE_IN_MIN_RMS

WARMUP_CHUNKS = 6      # ~0.5 s: learn the echo level before judging
BASELINE_CHUNKS = 25   # ~2 s of echo history
PREROLL_CHUNKS = 12    # ~1 s of audio handed to the next recording


def rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2))) if len(chunk) else 0.0


class BargeInDetector:
    def __init__(self, factor: float = BARGE_IN_FACTOR, min_rms: float = BARGE_IN_MIN_RMS,
                 needed: int = BARGE_IN_CHUNKS):
        self.factor, self.min_rms, self.needed = factor, min_rms, needed
        self.baseline: deque[float] = deque(maxlen=BASELINE_CHUNKS)
        self.recent: deque[np.ndarray] = deque(maxlen=PREROLL_CHUNKS)
        self.loud = 0
        self.seen = 0

    def echo_level(self) -> float:
        """The measured loudness of ULTRON's own voice in the mic (median of recent chunks)."""
        return float(np.median(self.baseline)) if self.baseline else 0.0

    def threshold(self) -> float:
        return max(self.min_rms, self.factor * self.echo_level())

    def feed(self, chunk: np.ndarray) -> bool:
        """Add one mic chunk; True when the user is talking over ULTRON."""
        self.seen += 1
        self.recent.append(chunk)
        level = rms(chunk)
        if self.seen <= WARMUP_CHUNKS:
            self.baseline.append(level)
            return False
        if level > self.threshold():
            self.loud += 1
        else:
            self.loud = 0
            self.baseline.append(level)  # only quiet chunks teach the echo level
        return self.loud >= self.needed

    def preroll(self) -> list[np.ndarray]:
        return list(self.recent)


def speech_level(voiced_rms: list[float]) -> float:
    """The typical loudness (median RMS, 16-bit units) of the chunks that counted as speech."""
    return float(np.median(voiced_rms)) if voiced_rms else 0.0
