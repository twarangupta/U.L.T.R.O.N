"""Download Piper voices into models/ (D25: say what, why, how big, show progress).

  python tools/download_voice.py              the current default voice (legacy Jarvis model)
  python tools/download_voice.py --list       candidate voices with licences
  python tools/download_voice.py joe bryce    candidate voices into models/voices/
  python tools/download_voice.py --all        every candidate that is not blocked

Licence column: ok = free for commercial use, flag = unclear, share-alike or
needs attribution (check before shipping), blocked = non-commercial or no
clear terms (refused unless --force-licence is passed, for listening only).
The legacy Jarvis download is removed once the owner picks the new voice (D35).
"""
import argparse
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en"

# name: (path under en/, licence status, licence and source dataset (from the MODEL_CARD), character)
VOICES = {
    "joe": ("en_US/joe/medium/en_US-joe-medium", "ok",
            "CC0, OHF-Voice/voice-datasets", "US male, neutral, medium depth"),
    "bryce": ("en_US/bryce/medium/en_US-bryce-medium", "ok",
              "public domain, recorded by Bryce Beattie himself", "US male, plain"),
    "john": ("en_US/john/medium/en_US-john-medium", "ok",
             "public domain, LibriVox readers", "US male, audiobook style"),
    "lessac": ("en_US/lessac/medium/en_US-lessac-medium", "flag",
               "Lessac Blizzard 2013 licence (custom text, read before shipping)", "US male-ish, clean"),
    "northern_english_male": ("en_GB/northern_english_male/medium/en_GB-northern_english_male-medium", "flag",
                              "CC-BY-SA 4.0, OpenSLR 83 (attribution and share-alike)", "UK male, northern"),
    "alan": ("en_GB/alan/medium/en_GB-alan-medium", "blocked",
             "Mimic3 apope dataset: 'All Rights Reserved Mycroft AI', terms unclear", "UK male, calm"),
    "ryan": ("en_US/ryan/high/en_US-ryan-high", "blocked",
             "CC BY-NC-SA 4.0 (non-commercial), RyanSpeech", "US male, high quality"),
}
LEGACY = {  # current default; imitates the film Jarvis, must not ship (D35)
    "onnx": "https://huggingface.co/jgkawell/jarvis/resolve/main/en/en_GB/jarvis/high/jarvis-high.onnx",
    "json": "https://huggingface.co/jgkawell/jarvis/resolve/main/en/en_GB/jarvis/high/jarvis-high.onnx.json",
}


def download_file(url: str, path: str, what: str, why: str) -> bool:
    """Download with a live progress line. Prints what it is, why and the size first."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ultron-voice-downloader"})
    try:
        with urllib.request.urlopen(req) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            size = f"{total / 1e6:.1f} MB" if total else "size unknown"
            print(f"\n{what}\n  why: {why}\n  size: {size}\n  to: {path}")
            done, start = 0, time.time()
            tmp = path + ".part"
            with open(tmp, "wb") as out:
                while chunk := resp.read(1 << 16):
                    out.write(chunk)
                    done += len(chunk)
                    rate = done / max(time.time() - start, 1e-6) / 1e6
                    pct = f"{100 * done // total}%" if total else f"{done / 1e6:.1f} MB"
                    sys.stdout.write(f"\r  {pct}  {done / 1e6:.1f} MB  {rate:.1f} MB/s   ")
                    sys.stdout.flush()
            os.replace(tmp, path)
            print("\n  done")
            return True
    except Exception as e:
        print(f"\n  FAILED {url}: {e}")
        return False


def fetch_voice(name: str, force_licence: bool = False) -> bool:
    rel, status, licence, _ = VOICES[name]
    if status == "blocked" and not force_licence:
        print(f"\nSkipping {name}: licence {licence}. Use --force-licence to fetch for listening only.")
        return False
    if status != "ok":
        print(f"\nNote: {name} licence is '{status}': {licence}")
    base = os.path.join(MODELS, "voices", os.path.basename(rel))
    ok = True
    for ext in (".onnx", ".onnx.json"):
        ok &= download_file(f"{HF}/{rel}{ext}", base + ext, f"Piper voice {name}{ext}",
                            "candidate ULTRON voice, rendered through the effect chain")
    return ok


def fetch_legacy() -> bool:
    ok = download_file(LEGACY["onnx"], os.path.join(MODELS, "ultron-voice.onnx"),
                       "Piper voice model (legacy default)", "current ULTRON voice until the owner picks a new one")
    ok &= download_file(LEGACY["json"], os.path.join(MODELS, "ultron-voice.onnx.json"),
                        "Piper voice config (legacy default)", "settings for the voice model")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force-licence", action="store_true")
    args = ap.parse_args()
    if args.list:
        for n, (_, status, lic, desc) in VOICES.items():
            print(f"{n:24} {status:8} {desc}; {lic}")
        return 0
    names = [n for n, v in VOICES.items() if v[1] != "blocked"] if args.all else args.names
    if not names:
        return 0 if fetch_legacy() else 1
    unknown = [n for n in names if n not in VOICES]
    if unknown:
        print(f"Unknown voice(s): {unknown}. Try --list.")
        return 2
    results = [fetch_voice(n, args.force_licence) for n in names]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
