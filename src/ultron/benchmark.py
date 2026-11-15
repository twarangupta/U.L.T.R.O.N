"""ultron.py --benchmark: show the chosen hardware profile and how fast it is.

Also runs on its own: venv\\Scripts\\python.exe benchmark.py

It needs no microphone. The test sentence is spoken by ULTRON's own Piper
voice into memory and then transcribed, so the numbers are comparable between
runs and machines.
"""
from __future__ import annotations

import os
import statistics
import time

import numpy as np

from ultron import paths

TEST_SENTENCE = "Open Chrome and turn the volume up."
RUNS = 3


def _voice_clip_16k() -> np.ndarray | None:
    """TEST_SENTENCE spoken by the Piper voice, as 16 kHz float32."""
    from math import gcd

    from piper import PiperVoice
    from scipy.signal import resample_poly

    path = next((p for p in (os.path.join(paths.MODELS_DIR, "ultron-voice.onnx"), os.path.join(paths.MODELS_DIR, "jarvis-high.onnx")) if os.path.exists(p)), None)
    if path is None:
        return None
    voice = PiperVoice.load(path)
    pcm = np.concatenate([np.frombuffer(c.audio_int16_bytes, dtype=np.int16) for c in voice.synthesize(TEST_SENTENCE)])
    rate = voice.config.sample_rate
    g = gcd(16000, rate)
    audio = resample_poly(pcm.astype(np.float32) / 32768.0, 16000 // g, rate // g)
    return np.concatenate([np.zeros(4000), audio, np.zeros(4000)]).astype(np.float32)


def _time_llm(model: str) -> list[float]:
    import ollama

    times = []
    for _ in range(2):
        start = time.perf_counter()
        ollama.chat(model=model, messages=[{"role": "user", "content": "Reply with one word: ready."}],
                    options={"num_predict": 8})
        times.append(time.perf_counter() - start)
    return times


def run_benchmark() -> int:
    import psutil

    from ultron.hardware import cuda_libraries_present, describe, detect_hardware, get_profile
    from ultron.stt.whisper import SpeechToText

    hw = detect_hardware()
    print("\n== ULTRON benchmark ==")
    print(f"Hardware : {describe(hw)}")
    ok, why = cuda_libraries_present()
    print(f"CUDA     : {'yes' if ok else 'no'} ({why})")
    profile = get_profile()
    print(f"Profile  : {profile.summary()}")
    for reason in profile.reasons:
        print(f"           - {reason}")

    stt = SpeechToText(profile)
    print(f"\nWhisper  : {stt.model_name} on {stt.device} ({stt.compute_type}), "
          f"load plus warm-up {stt.load_seconds:.1f} s")

    clip = _voice_clip_16k()
    if clip is None:
        print("           (no voice model, skipping the transcription test)")
    else:
        times, text = [], ""
        for _ in range(RUNS):
            start = time.perf_counter()
            text = stt.transcribe(clip)
            times.append(time.perf_counter() - start)
        print(f"           {len(clip) / 16000:.1f} s clip transcribed in {statistics.median(times):.2f} s "
              f"(median of {RUNS}): {text!r}")

    try:
        cold, warm = _time_llm(profile.llm_model)
        print(f"LLM      : {profile.llm_model}, first reply {cold:.2f} s, second {warm:.2f} s")
    except Exception as e:
        print(f"LLM      : {profile.llm_model} not reachable ({e})")

    rss = psutil.Process().memory_info().rss / 1024 ** 3
    print(f"RAM      : ULTRON process uses {rss:.2f} GB (Ollama runs separately)")
    print("\nOverride any choice with ULTRON_PROFILE, WHISPER_MODEL_SIZE, WHISPER_DEVICE,")
    print("WHISPER_COMPUTE_TYPE, WHISPER_CPU_THREADS or OLLAMA_MODEL in .env.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_benchmark())
