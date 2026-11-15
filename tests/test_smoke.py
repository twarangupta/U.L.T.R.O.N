"""Smoke tests: every module imports, and `python -m ultron --self-test` passes.

No microphone, speaker, GPU, Ollama or model files are needed.
"""
import importlib
import os
import pkgutil
import py_compile
import subprocess
import sys

import pytest

import ultron
from ultron.selftest import run_self_test

SRC = os.path.dirname(os.path.dirname(os.path.abspath(ultron.__file__)))

# These create the audio devices or load the Piper voice the moment they are imported
# (a module-level AudioHandler, Speaker), and app imports them. Check they compile instead.
IMPORT_HAS_SIDE_EFFECTS = {"ultron.audio.capture", "ultron.voice.speaker", "ultron.app"}


def _module_names() -> list[str]:
    return sorted(m.name for m in pkgutil.walk_packages(ultron.__path__, "ultron.") if m.name != "ultron.__main__")


@pytest.mark.parametrize("name", _module_names())
def test_module_imports(name):
    if name in IMPORT_HAS_SIDE_EFFECTS:
        path = os.path.join(SRC, *name.split(".")) + ".py"
        py_compile.compile(path, doraise=True)
        return
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name and e.name.split(".")[0] != "ultron":
            pytest.skip(f"optional library not installed here: {e.name}")
        raise


def test_self_test_passes(capsys):
    assert run_self_test() == 0
    assert "Self-test passed." in capsys.readouterr().out


def test_self_test_from_the_command_line():
    env = dict(os.environ, PYTHONPATH=SRC)
    result = subprocess.run([sys.executable, "-m", "ultron", "--self-test"], capture_output=True, text=True, env=env,
                            timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
