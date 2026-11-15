"""Voice activity detection: is there a human voice in this 80 ms block of the mic?

Silero VAD (MIT licence, ONNX, 2.3 MB) answers with a speech probability, so a
fan, a keyboard or a door does not count as speech and does not keep a recording
open. The recorder uses it to find the end of your sentence after about
VAD_END_SILENCE_SECONDS (0.35 s) instead of the old 0.6 s loudness timeout.

If the model file is missing and cannot be downloaded, `make_vad()` returns
LoudnessVad, the old "loud enough" check, so ULTRON still works.
"""
import os
import urllib.request

import numpy as np

from ultron import paths
from ultron.logger import logger

MODEL_URL = "https://github.com/snakers4/silero-vad/raw/v5.1.2/src/silero_vad/data/silero_vad.onnx"
MODEL_PATH = os.path.join(paths.MODELS_DIR, "silero_vad.onnx")
MODEL_SIZE_MB = 2.3
SAMPLE_RATE = 16000       # Silero needs exactly 16 kHz here
WINDOW = 512              # samples per model call (32 ms)
CONTEXT = 64              # samples of the previous window the model also sees
LOUDNESS_PEAK = 500       # fallback: a block whose peak is above this counts as speech


def model_available() -> bool:
    return os.path.exists(MODEL_PATH)


def download_model(log=print) -> bool:
    """Fetch the model once (D25: say what, why, how big; live progress). True when it is in place."""
    if model_available():
        return True
    log(f"Downloading the voice-activity model Silero VAD (about {MODEL_SIZE_MB} MB, one time). "
        "It tells your voice from noise, so ULTRON can stop listening about 0.25 s sooner after you finish.")
    tmp = MODEL_PATH + ".part"
    try:
        os.makedirs(paths.MODELS_DIR, exist_ok=True)
        with urllib.request.urlopen(MODEL_URL, timeout=20) as response, open(tmp, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done, shown = 0, -1
            while chunk := response.read(64 * 1024):
                out.write(chunk)
                done += len(chunk)
                percent = int(done * 100 / total) if total else int(done / (MODEL_SIZE_MB * 1e6 / 100))
                if percent // 10 != shown // 10:
                    shown = percent
                    log(f"  Silero VAD: {min(percent, 100)}% ({done / 1e6:.1f} MB)")
        os.replace(tmp, MODEL_PATH)
        return True
    except Exception as e:
        logger.warning(f"Could not download the Silero VAD model: {e}")
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


class LoudnessVad:
    """The old check: loud enough means speech. Same interface as SileroVad."""
    name = "loudness"
    end_silence_default = None  # the caller uses END_SILENCE_SECONDS

    def probability(self, block: np.ndarray) -> float:
        return 1.0 if len(block) and int(np.max(np.abs(block))) > LOUDNESS_PEAK else 0.0

    def reset(self):
        pass


class SileroVad:
    """One speech-probability stream. Each instance has its own memory; the model is shared."""
    name = "silero"
    _session = None

    @classmethod
    def load(cls):
        if cls._session is None:
            import onnxruntime as ort
            options = ort.SessionOptions()
            options.inter_op_num_threads = options.intra_op_num_threads = 1  # tiny model: one thread, no spin-up
            cls._session = ort.InferenceSession(MODEL_PATH, options, providers=["CPUExecutionProvider"])
        return cls._session

    def __init__(self):
        self.session = self.load()
        self.reset()

    def reset(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)
        self._pending = np.zeros(0, dtype=np.float32)
        self._last = 0.0

    def probability(self, block: np.ndarray) -> float:
        """Speech probability of an int16 block. 80 ms is 2.5 windows; the rest waits for the next block.
        The highest window wins, so a short word inside the block still counts."""
        samples = np.concatenate([self._pending, block.astype(np.float32) / 32768.0])
        best = None
        while len(samples) >= WINDOW:
            window, samples = samples[:WINDOW], samples[WINDOW:]
            x = np.concatenate([self._context, window])[None, :]
            out, self._state = self.session.run(
                None, {"input": x, "state": self._state, "sr": np.array(SAMPLE_RATE, dtype=np.int64)})
            self._context = x[0, -CONTEXT:]
            p = float(out[0, 0])
            best = p if best is None else max(best, p)
        self._pending = samples
        if best is not None:
            self._last = best
        return self._last


def make_vad(sample_rate: int = SAMPLE_RATE, download: bool = True):
    """Silero when possible, else the loudness check. Never raises."""
    if sample_rate != SAMPLE_RATE:
        logger.warning(f"Silero VAD needs {SAMPLE_RATE} Hz audio, not {sample_rate}: using the loudness check.")
        return LoudnessVad()
    try:
        if not model_available() and not (download and download_model()):
            raise FileNotFoundError(MODEL_PATH)
        vad = SileroVad()
        logger.info("Voice activity: Silero VAD")
        return vad
    except Exception as e:
        logger.warning(f"Silero VAD unavailable ({e}): using the old loudness check, which waits longer.")
        return LoudnessVad()
