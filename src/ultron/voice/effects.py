"""Voice effect chain for ULTRON: deeper, colder, a little metallic. numpy only.

Applied to each synthesized sentence chunk before playback. Order:
  1. pitch down   resample the chunk (a lower pitch AND a lower formant shift,
                  so the speaker sounds bigger, not just slowed). The speaker
                  asks Piper for a proportionally faster delivery
                  (length_scale_factor) so the final tempo is still VOICE_SPEED.
  2. metal        ring modulation (90 Hz carrier) plus a 2.3 ms comb: robotic edge.
  3. double       a faint copy 14 ms behind with a slowly wobbling delay (detune).
  4. reverb       dark synthetic room, FFT overlap-add convolution.
  5. limiter      soft clip so the sum never wraps around.

Click-free chunk boundaries: the ring modulator phase, the delay-line history
and the reverb tail all carry over from one chunk to the next, and flush()
returns the reverb tail at the end of a reply. All stages are vectorized (no
per-sample Python loops).

Settings come from .env: VOICE_PRESET (none, subtle, ultron, heavy) and
per-knob overrides VOICE_PITCH (semitones down), VOICE_METAL, VOICE_REVERB,
VOICE_DOUBLE (each 0 to 1).
"""
import os
from dataclasses import dataclass

import numpy as np

PRESETS = {
    "none": dict(pitch=0.0, metal=0.0, reverb=0.0, double=0.0, bass=0.0),
    "subtle": dict(pitch=1.5, metal=0.15, reverb=0.10, double=0.0, bass=0.0),
    "ultron": dict(pitch=3.0, metal=0.35, reverb=0.25, double=0.20, bass=0.0),
    "heavy": dict(pitch=4.0, metal=0.60, reverb=0.40, double=0.35, bass=0.0),
    # calm, close and cold: low and heavy in the chest, a faint metallic shimmer, a ghost double
    "silk": dict(pitch=2.5, metal=0.12, reverb=0.15, double=0.30, bass=0.5),
    # human and unhurried: no metal at all, deep and warm, a close, quiet room
    "calm": dict(pitch=3.0, metal=0.0, reverb=0.10, double=0.0, bass=0.6),
    "deep": dict(pitch=4.5, metal=0.0, reverb=0.12, double=0.10, bass=0.8),
    "cold": dict(pitch=3.5, metal=0.22, reverb=0.30, double=0.30, bass=0.7),
}
BASS_HZ = 220.0
BASS_TAPS = 129
RING_HZ = 90.0
COMB_SECONDS = 0.0023
DOUBLE_SECONDS = 0.014
DOUBLE_WOBBLE_SECONDS = 0.0015
DOUBLE_WOBBLE_HZ = 0.7
REVERB_T60 = 0.45           # seconds for the tail to fall 60 dB
REVERB_PREDELAY = 0.012
REVERB_DARK_HZ = 2200.0     # the room swallows everything above this


@dataclass(frozen=True)
class EffectSettings:
    pitch: float = 0.0      # semitones down
    metal: float = 0.0
    reverb: float = 0.0
    double: float = 0.0
    bass: float = 0.0       # low-end weight

    @property
    def active(self) -> bool:
        return any((self.pitch, self.metal, self.reverb, self.double, self.bass))

    @classmethod
    def from_env(cls, env=os.environ) -> "EffectSettings":
        name = env.get("VOICE_PRESET", "none").strip().lower()
        base = dict(PRESETS.get(name, PRESETS["none"]))
        for key in base:
            raw = env.get(f"VOICE_{key.upper()}", "").strip()
            if raw:
                try:
                    base[key] = float(raw)
                except ValueError:
                    pass
        return cls(
            pitch=min(max(base["pitch"], 0.0), 8.0),
            metal=min(max(base["metal"], 0.0), 1.0),
            reverb=min(max(base["reverb"], 0.0), 1.0),
            double=min(max(base["double"], 0.0), 1.0),
            bass=min(max(base["bass"], 0.0), 1.0),
        )


class EffectChain:
    def __init__(self, settings: EffectSettings, rate: int):
        self.s = settings
        self.rate = rate
        self.ratio = 2.0 ** (-settings.pitch / 12.0)   # read step; below 1 = lower and longer
        self._comb = max(int(COMB_SECONDS * rate), 1)
        self._max_delay = int((DOUBLE_SECONDS + DOUBLE_WOBBLE_SECONDS) * rate) + 4
        self._hist = np.zeros(max(self._comb, self._max_delay), dtype=np.float32)
        self._bass_kernel = self._make_bass_kernel()
        self._bass_hist = np.zeros(BASS_TAPS - 1, dtype=np.float32)
        self._phase = 0          # sample counter for the ring carrier and the wobble
        self._comb_hist = np.zeros(self._comb, dtype=np.float32)   # last input samples, for the comb
        self._ir = self._make_ir() if settings.reverb > 0 else None
        self._ir_fft: dict[int, np.ndarray] = {}
        self._tail = np.zeros(0 if self._ir is None else len(self._ir) - 1, dtype=np.float32)

    @property
    def length_scale_factor(self) -> float:
        """Multiply Piper's length_scale by this so the final tempo is unchanged."""
        return self.ratio

    def reset(self):
        self._hist[:] = 0
        self._comb_hist[:] = 0
        self._bass_hist[:] = 0
        self._phase = 0
        self._tail[:] = 0

    # ------------------------------------------------------------------

    def process(self, pcm: np.ndarray) -> np.ndarray:
        """int16 in, int16 out (longer than the input when pitch is lowered)."""
        if not self.s.active or len(pcm) == 0:
            return pcm
        x = pcm.astype(np.float32) / 32768.0
        x = self._pitch(x)
        if self.s.metal > 0:
            x = self._metal(x)
        if self.s.double > 0:
            x = self._double(x)
        else:
            self._remember(x)
        if self.s.bass > 0:
            x = self._bass(x)
        if self._ir is not None:
            x = self._reverb(x)
        return self._to_int16(x)

    def flush(self) -> np.ndarray:
        """Reverb tail left after the last chunk of a reply (empty without reverb)."""
        if self._ir is None or not len(self._tail):
            return np.zeros(0, dtype=np.int16)
        tail = self._tail * self.s.reverb * 0.6
        self._tail[:] = 0
        return self._to_int16(tail)

    # Stages ---------------------------------------------------------------

    def _pitch(self, x: np.ndarray) -> np.ndarray:
        if self.ratio == 1.0:
            return x
        pos = np.arange(0, len(x) - 1, self.ratio, dtype=np.float32)
        return np.interp(pos, np.arange(len(x), dtype=np.float32), x).astype(np.float32)

    def _remember(self, x: np.ndarray):
        """Keep the newest samples as history for the delay stages."""
        joined = np.concatenate([self._hist, x])
        self._hist = joined[-len(self._hist):]
        self._phase += len(x)

    def _metal(self, x: np.ndarray) -> np.ndarray:
        m = self.s.metal
        n = len(x)
        t = (self._phase + np.arange(n, dtype=np.float32)) / self.rate
        ring = x * np.sin(2 * np.pi * RING_HZ * t, dtype=np.float32)
        padded = np.concatenate([self._comb_hist, x])
        comb = padded[:n]                       # x delayed by _comb samples
        self._comb_hist = padded[-self._comb:].copy()
        return ((1 - 0.7 * m) * x + 0.7 * m * ring + 0.35 * m * comb).astype(np.float32)

    def _double(self, x: np.ndarray) -> np.ndarray:
        n = len(x)
        t = (self._phase + np.arange(n, dtype=np.float32)) / self.rate
        delay = (DOUBLE_SECONDS + DOUBLE_WOBBLE_SECONDS * np.sin(2 * np.pi * DOUBLE_WOBBLE_HZ * t)) * self.rate
        joined = np.concatenate([self._hist, x])
        idx = len(self._hist) + np.arange(n, dtype=np.float32) - delay
        copy = np.interp(idx, np.arange(len(joined), dtype=np.float32), joined).astype(np.float32)
        self._hist = joined[-len(self._hist):]
        self._phase += n
        return (x + 0.5 * self.s.double * copy).astype(np.float32)

    def _make_bass_kernel(self) -> np.ndarray:
        """Windowed-sinc low-pass; its output is mixed back in to add weight below 220 Hz."""
        n = np.arange(BASS_TAPS) - (BASS_TAPS - 1) / 2
        k = np.sinc(2 * BASS_HZ / self.rate * n) * np.hamming(BASS_TAPS)
        return (k / k.sum()).astype(np.float32)

    def _bass(self, x: np.ndarray) -> np.ndarray:
        """Add weight below 220 Hz. Linear-phase filter: the dry signal is delayed by the same
        64 samples (2.9 ms, carried across chunks) so the two stay in phase."""
        padded = np.concatenate([self._bass_hist, x])
        low = np.convolve(padded, self._bass_kernel, mode="valid")
        dry = padded[BASS_TAPS // 2: BASS_TAPS // 2 + len(x)]
        self._bass_hist = padded[-(BASS_TAPS - 1):].copy()
        return ((dry + 1.2 * self.s.bass * low) / (1 + 0.6 * self.s.bass)).astype(np.float32)

    def _make_ir(self) -> np.ndarray:
        rate = self.rate
        n = int(REVERB_T60 * rate)
        rng = np.random.default_rng(7)
        t = np.arange(n, dtype=np.float32) / rate
        ir = rng.standard_normal(n).astype(np.float32) * np.exp(-6.9 * t / REVERB_T60)
        ir[: int(REVERB_PREDELAY * rate)] = 0
        spec = np.fft.rfft(ir)
        freqs = np.fft.rfftfreq(n, 1 / rate)
        ir = np.fft.irfft(spec / (1 + (freqs / REVERB_DARK_HZ) ** 2), n).astype(np.float32)
        return ir / (np.sqrt(np.sum(ir ** 2)) + 1e-9)    # unit energy

    def _reverb(self, x: np.ndarray) -> np.ndarray:
        n, L = len(x), len(self._ir)
        size = 1 << int(np.ceil(np.log2(n + L - 1)))
        ir_f = self._ir_fft.get(size)
        if ir_f is None:
            ir_f = self._ir_fft[size] = np.fft.rfft(self._ir, size)
        wet = np.fft.irfft(np.fft.rfft(x, size) * ir_f, size)[: n + L - 1].astype(np.float32)
        wet[: len(self._tail)] += self._tail
        self._tail = wet[n:].copy()
        return x + self.s.reverb * 0.6 * wet[:n]

    @staticmethod
    def _to_int16(x: np.ndarray) -> np.ndarray:
        """Soft knee above 0.8 (same curve for every chunk, so levels never jump)."""
        mag = np.abs(x)
        knee = np.where(mag < 0.8, mag, 0.8 + 0.19 * np.tanh((mag - 0.8) / 0.19))
        return np.clip(np.sign(x) * knee * 32767.0, -32768, 32767).astype(np.int16)


SILENCE_LEVEL = 300   # int16 samples quieter than this at the edges count as silence


def trim_and_pause(pcm: np.ndarray, rate: int, pause_seconds: float) -> np.ndarray:
    """Cut near-silence from both ends (keeping 20 ms) and append a fixed pause."""
    loud = np.flatnonzero(np.abs(pcm.astype(np.int32)) > SILENCE_LEVEL)
    margin = int(0.02 * rate)
    if len(loud):
        pcm = pcm[max(loud[0] - margin, 0):loud[-1] + margin + 1]
    return np.concatenate([pcm, np.zeros(int(pause_seconds * rate), dtype=np.int16)])


def render_chunks(voice, syn_config, chain: EffectChain, spoken: str, pause_seconds: float):
    """Yield finished int16 audio for one text, one piece per Piper sentence.

    Each piece is trimmed, run through the effect chain and followed by the sentence
    pause; the reverb tail comes last. The chain starts from a clean state for every
    text. Not thread-safe: the caller holds the synthesis lock. Shared by the speaker
    and tools/voice_samples.py so the samples sound exactly like the assistant.
    """
    rate = voice.config.sample_rate
    pause = np.zeros(int(pause_seconds * rate), dtype=np.int16)
    chain.reset()
    for chunk in voice.synthesize(spoken, syn_config):
        raw = trim_and_pause(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16), rate, 0.0)
        yield np.concatenate([chain.process(raw), pause])
    tail = chain.flush()
    if len(tail):
        yield tail
