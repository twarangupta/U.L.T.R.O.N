"""Find the Whisper model that understands YOUR voice best.

Step 1, record (about 3 minutes, once):
    venv\\Scripts\\python.exe tools\\stt_benchmark.py record

    You read 16 short commands. Each is saved as a WAV file in
    recordings\\stt\\ (ignored by git, it is your voice).

Step 2, compare models (no microphone needed, re-run any time):
    venv\\Scripts\\python.exe tools\\stt_benchmark.py run

    Every model in --models is tried on the CPU, and on the GPU when CUDA
    works. For each it reports word error rate, how many commands came out
    exactly right, and the time per command. Results are written to
    recordings\\stt\\results.md. Models download on first use (see --help).

The settings match ULTRON's (beam 5, English, VAD filter, hotwords), so the
numbers are what you get when you talk to it. The tool also suggests entries
for corrections.json from the mistakes the recommended model made.
"""
from __future__ import annotations

import argparse
import difflib
import gc
import json
import os
import statistics
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import numpy as np  # noqa: E402

from ultron.commands.text import normalize  # noqa: E402

REC_DIR = os.getenv("STT_BENCH_DIR") or os.path.join(ROOT, "recordings", "stt")
SAMPLE_RATE = 16000

PHRASES = [
    "open chrome",
    "open vs code",
    "git status",
    "git push",
    "git pull",
    "switch branch to main",
    "volume up",
    "mute",
    "take a screenshot",
    "what time is it",
    "lock the pc",
    "type hello world",
    "check storage",
    "organize downloads",
    "go to sleep",
    "stop",
]

DEFAULT_MODELS = "base,base.en,small,small.en,medium.en,large-v3-turbo"
# Download sizes, so the user knows what --models costs (MB, approximate).
MODEL_MB = {"tiny": 75, "tiny.en": 75, "base": 145, "base.en": 145, "small": 485, "small.en": 485,
            "medium": 1530, "medium.en": 1530, "large-v3-turbo": 1620, "large-v3": 3100}
LATENCY_BUDGET_S = 1.0  # a model slower than this per command feels sluggish
CLOSE_WER_POINTS = 3.0  # accuracy this close to the best counts as a tie; then speed decides


# Recording -----------------------------------------------------------------

def _slug(i: int, phrase: str) -> str:
    return f"{i:02d}_{phrase.replace(' ', '_')}.wav"


def _record_once(noise_rms: float, max_seconds: float = 6.0) -> np.ndarray:
    """Record until 0.8 s of quiet after speech, or max_seconds."""
    import sounddevice as sd

    block = 1600  # 100 ms
    threshold = max(noise_rms * 3.0, 0.008)
    frames, started, quiet = [], False, 0
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=block) as stream:
        for _ in range(int(max_seconds * SAMPLE_RATE / block)):
            data, _ = stream.read(block)
            frames.append(data[:, 0].copy())
            loud = float(np.sqrt(np.mean(data ** 2))) > threshold
            if loud:
                started, quiet = True, 0
            elif started:
                quiet += 1
                if quiet >= 8:
                    break
    audio = np.concatenate(frames)
    return audio if started else np.zeros(0, dtype=np.float32)


def cmd_record(args) -> int:
    import sounddevice as sd
    import soundfile as sf

    os.makedirs(REC_DIR, exist_ok=True)
    print(f"Microphone: {sd.query_devices(kind='input')['name']}")
    print("Stay quiet for one second while I measure the room...")
    noise = sd.rec(SAMPLE_RATE, samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    noise_rms = float(np.sqrt(np.mean(noise ** 2)))
    print(f"Room noise level {noise_rms:.4f}. Speak the way you normally talk to ULTRON.\n")

    todo = [int(n) for n in args.only.split(",")] if args.only else range(1, len(PHRASES) + 1)
    for i in todo:
        phrase = PHRASES[i - 1]
        while True:
            input(f"[{i}/{len(PHRASES)}] Press Enter, then say:  \"{phrase}\"")
            audio = _record_once(noise_rms)
            if len(audio) == 0:
                print("   Heard nothing. Again.")
                continue
            print(f"   Got {len(audio) / SAMPLE_RATE:.1f} s.", end=" ")
            if input("Enter to keep, r to redo: ").strip().lower() != "r":
                break
        sf.write(os.path.join(REC_DIR, _slug(i, phrase)), audio, SAMPLE_RATE, subtype="PCM_16")

    with open(os.path.join(REC_DIR, "phrases.json"), "w", encoding="utf-8") as f:
        json.dump({_slug(i, p): p for i, p in enumerate(PHRASES, 1)}, f, indent=2)
    print(f"\nSaved to {REC_DIR}. Next: venv\\Scripts\\python.exe tools\\stt_benchmark.py run")
    return 0


# Scoring -------------------------------------------------------------------

def word_errors(reference: str, hypothesis: str) -> int:
    """Word-level edit distance (substitutions + insertions + deletions)."""
    ref, hyp = reference.split(), hypothesis.split()
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1]


def mishearings(reference: str, hypothesis: str) -> list[tuple[str, str]]:
    """(what was heard, what was said) pairs where the words differ.

    Each pair keeps one correct neighbouring word ("open pro" -> "open chrome"
    rather than "pro" -> "chrome"), so a correction only fires in context.
    """
    ref, hyp = reference.split(), hypothesis.split()
    pairs = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=hyp, b=ref, autojunk=False).get_opcodes():
        if op != "replace":
            continue
        if i1 > 0 and j1 > 0 and hyp[i1 - 1] == ref[j1 - 1]:
            i1, j1 = i1 - 1, j1 - 1
        elif i2 < len(hyp) and j2 < len(ref) and hyp[i2] == ref[j2]:
            i2, j2 = i2 + 1, j2 + 1
        pairs.append((" ".join(hyp[i1:i2]), " ".join(ref[j1:j2])))
    return pairs


# Running -------------------------------------------------------------------

def _load_recordings() -> list[tuple[str, np.ndarray]]:
    import soundfile as sf

    index = os.path.join(REC_DIR, "phrases.json")
    if not os.path.exists(index):
        return []
    with open(index, encoding="utf-8") as f:
        phrases = json.load(f)
    clips = []
    for name, phrase in phrases.items():
        path = os.path.join(REC_DIR, name)
        if os.path.exists(path):
            audio, rate = sf.read(path, dtype="float32")
            if rate == SAMPLE_RATE:
                clips.append((phrase, audio))
    return clips


def _vram_used_gb() -> float | None:
    import subprocess
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout
        return float(out.split()[0]) / 1024
    except Exception:
        return None


def benchmark_one(model_name, device, compute, clips, beam, threads):
    from faster_whisper import WhisperModel

    from ultron.config import WHISPER_HOTWORDS, WHISPER_LANGUAGE, WHISPER_VAD_FILTER

    start = time.perf_counter()
    model = WhisperModel(model_name, device=device, compute_type=compute, cpu_threads=threads)
    list(model.transcribe(np.zeros(8000, dtype=np.float32), beam_size=1, language=WHISPER_LANGUAGE)[0])
    load_s = time.perf_counter() - start
    vram = _vram_used_gb() if device == "cuda" else None

    rows = []
    for phrase, audio in clips:
        t = time.perf_counter()
        segments, _ = model.transcribe(audio, beam_size=beam, language=WHISPER_LANGUAGE,
                                       vad_filter=WHISPER_VAD_FILTER, hotwords=WHISPER_HOTWORDS or None)
        text = "".join(s.text for s in segments).strip()
        rows.append({"said": phrase, "heard": text, "seconds": time.perf_counter() - t})
    del model
    gc.collect()
    return load_s, vram, rows


def score(rows, fix=None):
    words = errors = exact = 0
    for row in rows:
        ref = normalize(row["said"])
        hyp = normalize(fix(row["heard"]) if fix else row["heard"])
        words += len(ref.split())
        errors += word_errors(ref, hyp)
        exact += ref == hyp
    return 100.0 * errors / max(words, 1), exact


def cmd_run(args) -> int:
    from ultron.stt import corrections
    from ultron.hardware import cuda_libraries_present, detect_hardware, describe

    clips = _load_recordings()
    if not clips:
        print("No recordings yet. First run: venv\\Scripts\\python.exe tools\\stt_benchmark.py record")
        return 1

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    devices = [d.strip() for d in args.devices.split(",")]
    hw = detect_hardware()
    if "cuda" in devices:
        ok, why = cuda_libraries_present()
        if not ok:
            print(f"GPU skipped: {why}")
            devices.remove("cuda")
    threads = max(1, min(hw.physical_cores, 8))
    total_mb = sum(MODEL_MB.get(m, 0) for m in models)
    print(f"Machine: {describe(hw)}")
    print(f"{len(clips)} recordings, models {models} on {devices}, beam {args.beam}.")
    print(f"Models not downloaded yet are fetched first (up to about {total_mb / 1024:.1f} GB in total).\n")

    results = []
    for device in devices:
        compute = args.gpu_compute if device == "cuda" else "int8"
        for name in models:
            label = f"{name} / {device} / {compute}"
            print(f"Testing {label} ...", flush=True)
            try:
                load_s, vram, rows = benchmark_one(name, device, compute, clips, args.beam, threads)
            except Exception as e:
                print(f"   failed: {e}")
                continue
            wer, exact = score(rows)
            wer_fixed, exact_fixed = score(rows, corrections.apply)
            med = statistics.median(r["seconds"] for r in rows)
            results.append(dict(model=name, device=device, compute=compute, load_s=load_s, vram_gb=vram,
                                wer=wer, exact=exact, wer_fixed=wer_fixed, exact_fixed=exact_fixed,
                                median_s=med, rows=rows))
            print(f"   WER {wer:.1f}%  exact {exact}/{len(rows)}  {med:.2f} s per command  load {load_s:.1f} s")

    if not results:
        return 1
    report = build_report(results, len(clips), hw)
    print("\n" + report)
    with open(os.path.join(REC_DIR, "results.md"), "w", encoding="utf-8") as f:
        f.write(report)
    with open(os.path.join(REC_DIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {os.path.join(REC_DIR, 'results.md')}")
    return 0


def recommend(results):
    """Accuracy first: among results close to the best WER, the fastest."""
    best = min(r["wer_fixed"] for r in results)
    close = [r for r in results if r["wer_fixed"] <= best + CLOSE_WER_POINTS]
    return min(close, key=lambda r: (r["median_s"], r["wer_fixed"]))


def build_report(results, n, hw) -> str:
    from ultron.hardware import describe

    ranked = sorted(results, key=lambda r: (r["wer_fixed"], r["median_s"]))
    pick = recommend(results)

    lines = [f"# Whisper accuracy on your voice ({n} commands)", "", f"Machine: {describe(hw)}", "",
             "| Model | Device | WER | Exact | WER with corrections | Sec per command | Load s | VRAM used GB |",
             "|---|---|---|---|---|---|---|---|"]
    for r in ranked:
        vram = f"{r['vram_gb']:.1f}" if r["vram_gb"] is not None else "-"
        lines.append(f"| {r['model']} | {r['device']} {r['compute']} | {r['wer']:.1f}% | {r['exact']}/{n} | "
                     f"{r['wer_fixed']:.1f}% ({r['exact_fixed']}/{n}) | {r['median_s']:.2f} | {r['load_s']:.1f} | {vram} |")
    lines += ["", f"Most accurate: {ranked[0]['model']} on {ranked[0]['device']}.",
              f"Recommended (fastest within {CLOSE_WER_POINTS:.0f} WER points of the best): "
              f"{pick['model']} on {pick['device']} ({pick['compute']}), {pick['median_s']:.2f} s per command"
              + ("" if pick["median_s"] <= LATENCY_BUDGET_S else f", over the {LATENCY_BUDGET_S:.0f} s budget"), "",
              f"## What {pick['model']} on {pick['device']} heard", ""]
    misses = Counter()
    for row in pick["rows"]:
        mark = "ok " if normalize(row["said"]) == normalize(row["heard"]) else "MISS"
        lines.append(f"- {mark} said \"{row['said']}\", heard \"{row['heard']}\"")
        misses.update(mishearings(normalize(row["said"]), normalize(row["heard"])))
    if misses:
        lines += ["", "## Suggested corrections.json entries", "",
                  "Add only the ones that are clearly mishearings and would never be meant literally:", "", "```"]
        lines += [f'  "{heard}": "{said}",' for (heard, said), _ in misses.most_common()]
        lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="read the test commands into the microphone")
    rec.add_argument("--only", help="re-record only these numbers, e.g. 3,7")
    run = sub.add_parser("run", help="compare Whisper models on the recordings")
    run.add_argument("--models", default=DEFAULT_MODELS,
                     help=f"comma list (default {DEFAULT_MODELS}; together about 4.4 GB to download)")
    run.add_argument("--devices", default="cpu,cuda", help="cpu, cuda or both (default both)")
    run.add_argument("--gpu-compute", default="int8_float16", help="GPU compute type (default int8_float16)")
    run.add_argument("--beam", type=int, default=5, help="beam size (ULTRON uses 5)")
    args = parser.parse_args()
    return cmd_record(args) if args.cmd == "record" else cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
