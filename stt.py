"""Speech to text with faster-whisper, using the hardware profile.

Known mishearings are fixed with corrections.json before the text is used.

If the GPU fails, either while loading or later during a transcription (out of
memory, a driver hiccup), ULTRON reloads Whisper on the CPU once and carries on.
"""
from __future__ import annotations

import time

import numpy as np

import corrections
from config import WHISPER_HOTWORDS, WHISPER_LANGUAGE, WHISPER_VAD_FILTER
from hardware import PROFILES, Profile, add_cuda_dll_paths
from logger import logger


def _cpu_fallback_model(profile: Profile) -> str:
    """The profile's CPU Whisper model (the GPU one may be too slow on a CPU)."""
    if profile.whisper_device != "cuda":
        return profile.whisper_model
    return PROFILES.get(profile.name, PROFILES["Lite"])["whisper"][0]


class SpeechToText:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.model = None
        self.device = profile.whisper_device
        self.model_name = profile.whisper_model
        self.compute_type = profile.whisper_compute_type
        self.load_seconds = 0.0
        self._load()

    def _load(self):
        from faster_whisper import WhisperModel

        if self.device == "cuda":
            add_cuda_dll_paths()
            try:
                self.model = self._load_and_warm(WhisperModel)
                return
            except Exception as e:
                logger.warning(f"Whisper on the GPU failed ({e}). Falling back to the CPU.")
                self._switch_to_cpu()
        self.model = self._load_and_warm(WhisperModel)

    def _load_and_warm(self, WhisperModel):
        start = time.perf_counter()
        logger.info(f"Loading Whisper '{self.model_name}' on {self.device} ({self.compute_type})...")
        model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.profile.whisper_cpu_threads,
        )
        # One tiny transcription proves the device really works (CUDA errors
        # show up here, not at load) and makes the first real command fast.
        segments, _ = model.transcribe(np.zeros(8000, dtype=np.float32), beam_size=1, language=WHISPER_LANGUAGE)
        list(segments)
        self.load_seconds = time.perf_counter() - start
        logger.info(f"Whisper ready on {self.device} in {self.load_seconds:.1f} s")
        return model

    def _switch_to_cpu(self):
        self.device = "cpu"
        self.compute_type = "int8"
        self.model_name = _cpu_fallback_model(self.profile)

    _hotword_text: str | None = None

    def _hotwords(self) -> str | None:
        """The configured hotwords plus the app names and window verbs ULTRON knows (built once)."""
        if not WHISPER_HOTWORDS:
            return None
        if self._hotword_text is None:
            try:
                from commands import apps
                extra = ", ".join(apps.hotword_names())
            except Exception:
                extra = ""
            self._hotword_text = f"{WHISPER_HOTWORDS}, {extra}" if extra else WHISPER_HOTWORDS
            logger.info(f"Whisper hotwords: {self._hotword_text}")
        return self._hotword_text

    def transcribe(self, audio: np.ndarray) -> str:
        """Text for one utterance, or "" on silence or error."""
        if len(audio) == 0:
            return ""
        try:
            return self._run(audio)
        except Exception as e:
            if self.device != "cuda":
                logger.error(f"Transcription error: {e}")
                return ""
            logger.warning(f"GPU transcription failed ({e}). Reloading Whisper on the CPU.")
            try:
                self._switch_to_cpu()
                self._load()
                return self._run(audio)
            except Exception as e2:
                logger.error(f"Transcription error after CPU fallback: {e2}")
                return ""

    def _run(self, audio: np.ndarray) -> str:
        segments, _info = self.model.transcribe(
            audio,
            beam_size=5,
            language=WHISPER_LANGUAGE,
            vad_filter=WHISPER_VAD_FILTER,
            hotwords=self._hotwords(),
        )
        heard = "".join(seg.text for seg in segments).strip()
        fixed = corrections.apply(heard)
        if fixed != heard:
            logger.info(f"Corrected {heard!r} -> {fixed!r}")
        return fixed
