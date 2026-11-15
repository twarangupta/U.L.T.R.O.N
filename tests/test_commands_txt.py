"""docs/COMMANDS.md must be exactly what the registry generates (tools/gen_commands_txt.py)."""
import os
import sys


import gen_commands_txt  # noqa: E402


def test_commands_txt_is_generated_from_the_registry():
    with open(gen_commands_txt.OUT, encoding="utf-8") as f:
        current = f.read()
    assert current == gen_commands_txt.render(), (
        "docs/COMMANDS.md is stale: run venv\\Scripts\\python.exe tools\\gen_commands_txt.py")
