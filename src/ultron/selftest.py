"""python -m ultron --self-test: prove the install is wired together without touching hardware.

Loads the settings, the command registry (every command's declaration, examples
and schema) and the hardware profile. It opens no microphone, plays no sound and
loads no model, so it is safe to run while ULTRON is running and on a CI runner.
Exit code 0 means everything checked out; 1 means at least one check failed.
"""
from __future__ import annotations

import os


def _check_config() -> str:
    from ultron import config, paths
    assert config.SAMPLE_RATE > 0 and config.OLLAMA_SYSTEM_PROMPT
    assert os.path.isdir(paths.CONFIG_DIR), f"missing folder {paths.CONFIG_DIR}"
    return f"wake phrase '{config.WAKE_PHRASE}', config folder found"


def _check_registry() -> str:
    from ultron import commands  # noqa: F401  (importing registers every command)
    from ultron.commands import registry
    from ultron.commands.router import tool_schemas

    cmds = registry.commands()
    assert cmds, "the command registry is empty"
    names = [c.name for c in cmds]
    assert len(names) == len(set(names)), "duplicate command names"
    for c in cmds:
        assert c.description and c.examples, f"command {c.name} has no description or examples"
    assert len(tool_schemas(names)) == len(cmds)
    return f"{len(cmds)} commands registered"


def _check_hardware() -> str:
    from ultron import hardware
    hw = hardware.detect_hardware()
    profile = hardware.choose_profile(hw, installed={})
    return f"{hardware.describe(hw)} -> profile {profile.name}"


CHECKS = [
    ("config", _check_config),
    ("command registry", _check_registry),
    ("hardware profile", _check_hardware),
]


def run_self_test() -> int:
    failed = 0
    for name, check in CHECKS:
        try:
            print(f"ok    {name}: {check()}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print("Self-test passed." if not failed else f"Self-test failed ({failed} check(s)).")
    return 1 if failed else 0
