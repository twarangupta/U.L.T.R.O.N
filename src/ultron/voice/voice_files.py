"""Which Piper voice file to load, with a clear fallback. No audio or model imports, so it is testable."""
import os

from ultron import paths
from ultron.config import VOICE_MODEL
from ultron.logger import logger


def model_paths(name: str = VOICE_MODEL) -> list[str]:
    """Voice files to try, best first. name: empty, a models/voices/ name, or a path."""
    legacy = [
        os.getenv("VOICE_MODEL_PATH", os.path.join(paths.MODELS_DIR, "ultron-voice.onnx")),
        os.path.join(paths.MODELS_DIR, "jarvis-high.onnx"),  # name used by older installs
    ]
    if not name or name.lower() in ("jarvis", "ultron-voice"):
        return legacy
    if os.path.isabs(name) or name.endswith(".onnx"):
        chosen = name
    else:
        chosen = os.path.join(paths.MODELS_DIR, "voices", name + ".onnx")
    return [chosen, *legacy]



def pick_model(candidates: list[str]) -> str | None:
    """First voice file that exists. If the chosen one is missing, say how to get it."""
    for i, path in enumerate(candidates):
        if os.path.exists(path):
            if i:
                logger.warning(f"Voice {os.path.basename(candidates[0])} is missing; using "
                               f"{os.path.basename(path)} instead.")
            return path
        if i == 0:
            logger.warning(f"Voice file not found: {path}. Download it with: "
                           "python tools/download_voice.py joe")
    return None
