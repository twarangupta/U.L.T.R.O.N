"""PyInstaller entry point: the same as `python -m ultron`, plus --import-check.

--import-check imports every heavy library the app uses (speech, wake word, audio, Windows COM and WinRT)
WITHOUT opening a microphone, a speaker or a model. The normal --self-test does not touch most of them, so
this is what proves the frozen build really contains them. Used by packaging/build.ps1 and CI.
"""
import importlib
import sys

HEAVY_MODULES = [
    "faster_whisper", "ctranslate2", "onnxruntime", "openwakeword", "piper", "model2vec", "tokenizers",
    "av", "numpy", "scipy", "psutil", "ollama", "sounddevice", "yaml", "pyautogui", "pyperclip",
    "pycaw.pycaw", "comtypes", "comtypes.client", "winrt.windows.devices.radios", "winrt.windows.foundation",
    "winrt.windows.media.ocr", "winrt.windows.graphics.imaging", "winrt.windows.storage.streams",
]


def import_check() -> int:
    failed = 0
    for name in HEAVY_MODULES:
        try:
            importlib.import_module(name)
            print(f"ok    import {name}")
        except Exception as e:  # report every failure, not just the first
            failed += 1
            print(f"FAIL  import {name}: {type(e).__name__}: {e}")
    print("Import check passed." if not failed else f"Import check failed ({failed}).")
    return 1 if failed else 0


if __name__ == "__main__":
    if "--import-check" in sys.argv:
        sys.exit(import_check())
    from ultron.__main__ import main
    sys.exit(main())
