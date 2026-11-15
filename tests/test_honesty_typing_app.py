"""D39 tests that need app.py (process priority, listen windows). app.py imports the wake word and the
voice at import time, so these skip where openwakeword or piper is not installed (CI)."""
import os
import subprocess
import sys
import types

import pytest

pytest.importorskip("openwakeword")
pytest.importorskip("piper")

from ultron import app, config  # noqa: E402

# ---- process priority handle ----
def test_priority_call_declares_handle_types(monkeypatch):
    from ctypes import wintypes

    class Fn:
        def __init__(self, ret):
            self.ret, self.restype, self.argtypes = ret, None, None

        def __call__(self, *a):
            return self.ret

    k = types.SimpleNamespace(GetCurrentProcess=Fn(-1), SetPriorityClass=Fn(1))
    monkeypatch.setattr(app, "_kernel32", lambda: k)
    monkeypatch.setattr(app.sys, "platform", "win32")
    assert app.raise_priority() is True
    assert k.GetCurrentProcess.restype is wintypes.HANDLE
    assert k.SetPriorityClass.argtypes == [wintypes.HANDLE, wintypes.DWORD]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_priority_really_works_in_a_throwaway_process():
    code = ("import ctypes; from ctypes import wintypes; from ultron import app; ok = app.raise_priority();"
            "k = ctypes.windll.kernel32; k.GetPriorityClass.restype = wintypes.DWORD;"
            "k.GetCurrentProcess.restype = wintypes.HANDLE; k.GetPriorityClass.argtypes = [wintypes.HANDLE];"
            "print(ok, hex(k.GetPriorityClass(k.GetCurrentProcess())))")
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PYTHONPATH": "src"})
    assert run.stdout.strip().splitlines()[-1] == "True 0x8000", run.stdout + run.stderr


# ---- short listen windows ----
def test_listen_window_is_five_seconds():
    assert config.CONFIRM_LISTEN_SECONDS == 5.0 and app.CONFIRM_LISTEN_SECONDS == 5.0
