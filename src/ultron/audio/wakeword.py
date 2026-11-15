import os
import numpy as np
from openwakeword.model import Model
from ultron.config import WAKE_WORD_MODEL, WAKE_WORD_THRESHOLD, WAKE_PHRASE, HEY_ULTRON_MODEL_PATH, FALLBACK_WAKE_WORD_MODEL
from ultron.logger import logger

def _ensure_model_files():
    """Download openWakeWord's feature models and the built-in wake word if missing.

    A fresh Python environment has the library but not these files, which
    used to stop ULTRON at startup with "File doesn't exist".
    """
    try:
        from openwakeword.utils import download_models
        builtin = [] if os.path.exists(WAKE_WORD_MODEL) else [WAKE_WORD_MODEL]
        download_models(model_names=builtin)  # skips files that already exist
    except Exception as e:
        logger.warning(f"Could not download wake word model files: {e}")


class WakeWordDetector:
    """
    Wraps the OpenWakeWord library to monitor streaming audio chunks
    and detect the wake word.
    """
    def __init__(self):
        logger.info(f"Initializing OpenWakeWord with model: {WAKE_WORD_MODEL}")
        if WAKE_WORD_MODEL == FALLBACK_WAKE_WORD_MODEL:
            logger.warning(
                f"Custom wake word model not found at {HEY_ULTRON_MODEL_PATH}. "
                "Falling back to the built-in 'hey_jarvis' model: say \"Hey Jarvis\" for now. "
                "See docs/WAKE_WORD_TRAINING.md to train \"Hey Ultron\"."
            )
        logger.info(f"Wake phrase: \"{WAKE_PHRASE}\"")

        _ensure_model_files()

        # OpenWakeWord accepts file paths to custom models (the prediction
        # key is the file name without extension, e.g. 'hey_ultron'),
        # or names of built-in models
        if os.path.exists(WAKE_WORD_MODEL):
            # If a custom path is specified, let openwakeword determine the framework or force onnx
            if WAKE_WORD_MODEL.endswith(".onnx"):
                self.model = Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")
            else:
                self.model = Model(wakeword_models=[WAKE_WORD_MODEL])
        else:
            self.model = Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")
            
        # Get the internal key used to access prediction buffers
        self.model_key = list(self.model.models.keys())[0]
        logger.info(f"Wake word model loaded. Key name: {self.model_key}")

    def is_wake_word(self, chunk: np.ndarray) -> bool:
        """
        Processes a single chunk of audio (1280 samples at 16000Hz).
        Returns True if the wake word is detected above the threshold.
        """
        # Run prediction on the chunk
        self.model.predict(chunk)
        
        # Get the latest prediction score
        score = self.model.prediction_buffer[self.model_key][-1]
        
        if score >= WAKE_WORD_THRESHOLD:
            logger.info(f"Wake Word Triggered. Confidence: {score:.2f}")
            return True
            
        return False

    def reset(self):
        """Resets the model's prediction buffer and internal state."""
        self.model.reset()
