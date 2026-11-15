"""commands.txt must be exactly what the registry generates (tools/gen_commands_txt.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import gen_commands_txt  # noqa: E402


def test_commands_txt_is_generated_from_the_registry():
    with open(gen_commands_txt.OUT, encoding="utf-8") as f:
        current = f.read()
    assert current == gen_commands_txt.render(), (
        "commands.txt is stale: run venv\\Scripts\\python.exe tools\\gen_commands_txt.py")
