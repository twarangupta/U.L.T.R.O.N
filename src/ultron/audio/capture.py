"""Microphone input: opens the mic, records one phrase and ends it after a pause.

Creates one AudioHandler (PyAudio) when imported. Silence is found by loudness (RMS)."""

import pyaudio
import numpy as np
import sys
import select
from ultron.audio.bargein import speech_level
from ultron.config import SAMPLE_RATE, CHUNK_SIZE
from ultron.logger import logger

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
    """
    Manages microphone input streams.
    Provides methods to stream raw chunks for wake word detection,
    and to record complete phrases with basic silence detection for Whisper.
    """
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.stream = None

    def start_stream(self) -> bool:
        """Starts the microphone input stream. Returns True on success, False on failure."""
        if self.stream is not None:
            self.stop_stream()
            
        try:
            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE
            )
            return True
        except Exception as e:
            logger.error(f"Failed to open microphone stream: {e}. Please check audio input permissions/device connection.")
            self.stream = None
            return False

    def stop_stream(self):
        """Stops and closes the microphone stream."""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error closing stream: {e}")
            self.stream = None

    def read_chunk(self) -> np.ndarray:
        """
        Reads a single chunk of audio from the stream.
        Returns a numpy array of int16 samples.
        """
        try:
            if self.stream is None or not self.stream.is_active():
                self.start_stream()
        except OSError:
            self.stream = None
            self.start_stream()
            
        try:
            data = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
            return np.frombuffer(data, dtype=np.int16)
        except Exception:
            # Underflow/Overflow or hardware issues
            return np.zeros(CHUNK_SIZE, dtype=np.int16)

    last_speech_level = 0.0  # median RMS of the last recorded phrase's speech chunks (for tuning barge-in)

    def record_phrase(self, silence_threshold=500, silence_timeout_seconds=0.8, max_seconds=10.0,
                      preroll=None) -> np.ndarray:
        """
        Records the microphone stream until silence is detected or max duration is reached.
        Returns a normalized float32 numpy array, ready for Whisper.
        preroll: chunks already captured (the user talked over ULTRON); the
        recording continues from them, so their first words are kept.
        """
        logger.info("Listening for speech...")
        self.start_stream()

        recorded_frames = list(preroll or [])
        silent_chunks = 0
        
        # Calculate how many chunks represent the silence timeout
        # Each chunk is 1280 samples at 16000Hz = 80ms (0.08 seconds)
        chunk_duration = CHUNK_SIZE / SAMPLE_RATE
        max_silent_chunks = int(silence_timeout_seconds / chunk_duration)
        max_total_chunks = int(max_seconds / chunk_duration)
        
        started_speaking = bool(recorded_frames)
        voiced_rms: list[float] = []  # loudness of the chunks that counted as speech

        for _ in range(max_total_chunks):
            # If the user presses any key, stop recording and process immediately
            if check_keyboard_hit():
                clear_keyboard_hit()
                logger.info("Recording stopped by user keyboard input")
                break
                
            chunk = self.read_chunk()
            recorded_frames.append(chunk)
            
            # Simple volume threshold check (using Root Mean Square or max amplitude)
            amplitude = np.max(np.abs(chunk))
            
            if amplitude > silence_threshold:
                voiced_rms.append(float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2))))
                if not started_speaking:
                    # Voice activity detected
                    started_speaking = True
                silent_chunks = 0
            else:
                if started_speaking:
                    silent_chunks += 1
                    if silent_chunks >= max_silent_chunks:
                        # Finished speaking
                        break
        
        # Clean up stream after phrase is recorded
        self.stop_stream()
        self.last_speech_level = speech_level(voiced_rms)
        if voiced_rms:
            logger.info(f"speech level: median rms {self.last_speech_level:.0f}, "
                        f"peak rms {max(voiced_rms):.0f} over {len(voiced_rms)} chunks")
        
        if not recorded_frames:
            return np.zeros(0, dtype=np.float32)
            
        # Concatenate and convert to float32 normalized in [-1.0, 1.0]
        audio_data = np.concatenate(recorded_frames)
        return audio_data.astype(np.float32) / 32768.0

    def terminate(self):
        """Clean up PyAudio resource."""
        self.stop_stream()
        self.pa.terminate()

# Global audio handler instance
audio_handler = AudioHandler()
