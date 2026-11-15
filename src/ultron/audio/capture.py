"""Microphone input: one always-open stream that wake word, recorder and barge-in all read from.

A sounddevice InputStream (16 kHz mono, 80 ms blocks) pushes every block into a ring buffer. The
readers take blocks from it in order, so switching between "waiting for the wake word", "recording
a phrase" and "listening while ULTRON talks" never closes or reopens the device (no gaps, no
start-up delay). Nothing is opened at import: the first start_stream() opens the mic.

Where a phrase ends is decided by voice activity detection (audio/vad.py)."""

import select
import sys
import threading
import time
from collections import deque

import numpy as np

from ultron.audio.bargein import speech_level
from ultron.audio.vad import make_vad
from ultron.config import CHUNK_SIZE, END_SILENCE_SECONDS, SAMPLE_RATE, VAD_END_SILENCE_SECONDS, VAD_THRESHOLD
from ultron.logger import logger

RING_BLOCKS = 125          # 10 s of audio; if nobody reads, the oldest blocks are dropped
READ_TIMEOUT = 1.0         # seconds to wait for the next block before giving up (device stalled)
LEAD_BLOCKS = 6            # ~0.5 s of audio kept from before the first word


def check_keyboard_hit() -> bool:
    """Cross-platform check for keyboard press."""
    if sys.platform == "win32":
        try:
            import msvcrt
            return msvcrt.kbhit()
        except ImportError:
            return False
    else:
        # Non-blocking stdin check on Unix/macOS
        rlist, _, _ = select.select([sys.stdin], [], [], 0)
        return bool(rlist)


def clear_keyboard_hit():
    """Consumes/clears the pressed key to prevent buffering issues."""
    if sys.platform == "win32":
        try:
            import msvcrt
            if msvcrt.kbhit():
                msvcrt.getch()
        except ImportError:
            pass
    else:
        # Read from stdin to consume the keypress
        rlist, _, _ = select.select([sys.stdin], [], [], 0)
        if rlist:
            try:
                sys.stdin.read(1)
            except Exception:
                pass


class AudioHandler:
    """The shared microphone: a ring buffer fed by one stream, read by whoever needs audio now."""

    last_speech_level = 0.0   # median RMS of the last phrase's speech blocks (for tuning barge-in)
    last_end_silence = END_SILENCE_SECONDS   # the pause that ended the last phrase (for the timing log)

    def __init__(self, vad=None):
        self._stream = None
        self._blocks: deque[np.ndarray] = deque(maxlen=RING_BLOCKS)
        self._ready = threading.Condition()
        self._vad = vad
        self._open_stream = self._open_sounddevice   # tests replace this with a fake

    # --- the stream and the ring buffer -----------------------------------

    def _open_sounddevice(self):
        import sounddevice as sd

        def on_audio(indata, frames, time_info, status):
            self.push(indata[:, 0].copy())

        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=CHUNK_SIZE, latency="low", callback=on_audio)
        stream.start()
        return stream

    def push(self, block: np.ndarray):
        """Add one block to the ring buffer (called from the audio thread)."""
        with self._ready:
            self._blocks.append(block)
            self._ready.notify_all()

    def _is_open(self) -> bool:
        stream = self._stream
        return stream is not None and getattr(stream, "active", True)

    def start_stream(self) -> bool:
        """Begin listening now: drop audio that piled up while nobody read, and open the mic if it is
        not open yet (the first call, or after the device failed). Returns False when it cannot open."""
        with self._ready:
            self._blocks.clear()
        if self._is_open():
            return True
        self._close()
        try:
            self._stream = self._open_stream()
            return True
        except Exception as e:
            logger.error(f"Failed to open microphone stream: {e}. Please check audio input permissions/device connection.")
            self._stream = None
            return False

    def stop_stream(self):
        """Kept for the callers that switch modes. The mic stays open: the next reader just starts
        from the newest audio (start_stream)."""

    def _close(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                logger.error(f"Error closing stream: {e}")

    def terminate(self):
        """Close the microphone (at shutdown)."""
        self._close()

    def read_chunk(self) -> np.ndarray:
        """The next 80 ms block (int16 samples), waiting for it if needed.
        Zeros if the device stalls for READ_TIMEOUT seconds."""
        if not self._is_open() and not self.start_stream():
            return np.zeros(CHUNK_SIZE, dtype=np.int16)
        with self._ready:
            if not self._blocks:
                self._ready.wait(READ_TIMEOUT)
            if self._blocks:
                return self._blocks.popleft()
        return np.zeros(CHUNK_SIZE, dtype=np.int16)

    # --- voice activity ----------------------------------------------------

    @property
    def vad(self):
        if self._vad is None:
            self._vad = make_vad(SAMPLE_RATE)   # Silero (downloads once), or the loudness check
        return self._vad

    def new_vad(self):
        """A second, independent voice detector for barge-in (same model, own memory), or None
        when only the loudness fallback is available."""
        return type(self.vad)() if self.vad.name == "silero" else None

    # --- recording ---------------------------------------------------------

    def record_phrase(self, silence_timeout_seconds=None, max_seconds=10.0, preroll=None) -> np.ndarray:
        """
        Records until you stop talking (a pause of silence_timeout_seconds after speech; default
        VAD_END_SILENCE_SECONDS, or END_SILENCE_SECONDS with the loudness fallback) or max_seconds pass.
        Returns a float32 array in [-1, 1] for Whisper, or an empty array when nobody spoke
        (silence is never sent to Whisper).
        preroll: blocks already captured (the user talked over ULTRON); the recording continues
        from them, so their first words are kept.
        """
        logger.info("Listening for speech...")
        self.start_stream()
        vad = self.vad
        vad.reset()
        if silence_timeout_seconds is None:
            silence_timeout_seconds = VAD_END_SILENCE_SECONDS if vad.name == "silero" else END_SILENCE_SECONDS
        self.last_end_silence = silence_timeout_seconds

        block_seconds = CHUNK_SIZE / SAMPLE_RATE   # 0.08 s
        max_silent_blocks = max(1, round(silence_timeout_seconds / block_seconds))
        max_total_blocks = int(max_seconds / block_seconds)
        deadline = time.monotonic() + max_seconds + 2.0   # a stalled device cannot hold us for long

        frames = list(preroll or [])
        lead: deque[np.ndarray] = deque(maxlen=LEAD_BLOCKS)   # quiet audio before the first word
        started_speaking = bool(frames)
        silent_blocks = 0
        voiced_rms: list[float] = []

        for _ in range(max_total_blocks):
            if check_keyboard_hit():   # any key: stop and process now
                clear_keyboard_hit()
                logger.info("Recording stopped by user keyboard input")
                break
            if time.monotonic() > deadline:
                break
            chunk = self.read_chunk()
            if vad.probability(chunk) >= VAD_THRESHOLD:
                voiced_rms.append(float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2))))
                if not started_speaking:
                    started_speaking = True
                    frames.extend(lead)
                frames.append(chunk)
                silent_blocks = 0
            elif started_speaking:
                frames.append(chunk)
                silent_blocks += 1
                if silent_blocks >= max_silent_blocks:
                    break   # finished speaking
            else:
                lead.append(chunk)

        self.last_speech_level = speech_level(voiced_rms)
        if voiced_rms:
            logger.info(f"speech level: median rms {self.last_speech_level:.0f}, "
                        f"peak rms {max(voiced_rms):.0f} over {len(voiced_rms)} chunks")

        if not frames or not started_speaking:
            return np.zeros(0, dtype=np.float32)  # nobody spoke: nothing for Whisper to hear
        return np.concatenate(frames).astype(np.float32) / 32768.0


# One shared microphone. Creating it opens nothing; the first start_stream() does.
audio_handler = AudioHandler()
