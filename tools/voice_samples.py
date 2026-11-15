"""Render voice samples for listening: every voice x every effect preset, to WAV files.

Silent: plays nothing, only writes files to results/voice_samples/ and an index.md.

  python tools/voice_samples.py                  all voices in models/voices/ (+ the legacy default)
  python tools/voice_samples.py --voices en_US-joe-medium --presets none ultron
  python tools/voice_samples.py --speed 0.9

Pick one, then set in .env:  VOICE_MODEL=<voice>  VOICE_PRESET=<preset>
"""
import argparse
import os
import sys
import time
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from piper import PiperVoice  # noqa: E402
from piper.config import SynthesisConfig  # noqa: E402

from ultron import persona  # noqa: E402
from ultron.voice.effects import PRESETS, EffectChain, EffectSettings, render_chunks  # noqa: E402
from ultron.voice.tts_text import prepare_for_speech  # noqa: E402

MODELS = os.path.join(ROOT, "models")
OUT = os.path.join(ROOT, "results", "voice_samples")
LINES = {
    "persona": persona.GREETINGS[0],
    "command": "Opening Chrome. Volume set to forty percent.",
    "answer": ("A kernel is the core of an operating system. It decides which program gets the "
               "processor, manages memory, and talks to the hardware so that applications do not "
               "have to. If it fails, everything fails. Much like a human in the morning."),
}


def find_voices() -> dict[str, str]:
    voices = {}
    vdir = os.path.join(MODELS, "voices")
    if os.path.isdir(vdir):
        for f in sorted(os.listdir(vdir)):
            if f.endswith(".onnx"):
                voices[f[:-5]] = os.path.join(vdir, f)
    legacy = os.path.join(MODELS, "ultron-voice.onnx")
    if os.path.exists(legacy):
        voices["legacy-default"] = legacy
    return voices


def write_wav(path: str, pcm: np.ndarray, rate: int):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.astype(np.int16).tobytes())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voices", nargs="*", help="voice names (default: all found)")
    ap.add_argument("--presets", nargs="*", default=list(PRESETS))
    ap.add_argument("--speed", type=float, default=0.9, help="final pace, like VOICE_SPEED")
    ap.add_argument("--pause", type=float, default=0.13)
    args = ap.parse_args()

    voices = find_voices()
    if args.voices:
        voices = {k: v for k, v in voices.items() if k in args.voices}
    if not voices:
        print("No voices found. Run: python tools/download_voice.py --all")
        return 1
    os.makedirs(OUT, exist_ok=True)

    rows, timings = [], []
    for name, path in voices.items():
        voice = PiperVoice.load(path)
        rate = voice.config.sample_rate
        for preset in args.presets:
            chain = EffectChain(EffectSettings.from_env({"VOICE_PRESET": preset}), rate)
            cfg = SynthesisConfig(length_scale=chain.length_scale_factor / args.speed)
            for label, text in LINES.items():
                start = time.perf_counter()
                parts = list(render_chunks(voice, cfg, chain, prepare_for_speech(text), args.pause))
                took = time.perf_counter() - start
                pcm = np.concatenate(parts)
                file = os.path.abspath(os.path.join(OUT, f"{name}__{preset}__{label}.wav"))
                write_wav(file, pcm, rate)
                seconds = len(pcm) / rate
                timings.append((name, preset, label, seconds, took))
                rows.append((name, preset, label, seconds, file))
                print(f"{name:42} {preset:7} {label:8} {seconds:5.1f} s audio, {took:4.1f} s to render")

    with open(os.path.join(OUT, "index.md"), "w", encoding="utf8") as f:
        f.write("# Voice samples\n\nSet VOICE_MODEL and VOICE_PRESET in .env to the one you like.\n\n")
        for label, text in LINES.items():
            f.write(f"- {label}: {text}\n")
        f.write("\n| voice | preset | line | seconds | file |\n|---|---|---|---|---|\n")
        for name, preset, label, seconds, file in rows:
            f.write(f"| {name} | {preset} | {label} | {seconds:.1f} | {file} |\n")
    print(f"\nWrote {len(rows)} files and index.md to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
