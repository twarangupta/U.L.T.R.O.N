"""ULTRON's voice commands.

Every command is declared once in the registry (commands/registry.py, D30).
Importing this package registers all of them; the router (commands/router.py)
picks one for a sentence in three stages: rules, meaning, then the LLM's tool call.
"""
from typing import Callable

# Importing a module registers its commands. Order only breaks priority ties.
from commands import general, risky, clock, memory_cmds, activity_cmds, windows  # noqa: F401
from commands import system, git_helpers, developer  # noqa: F401
from commands.router import Interaction, _ConfirmOnly, route

# Asks the user a yes/no question by voice. Gets the spoken prompt,
# returns True only if the user said "confirm".
ConfirmFn = Callable[[str], bool]


def execute_command(text: str, confirm: ConfirmFn | None = None, io: Interaction | None = None) -> str | None:
    """Rules and the meaning matcher. Returns the reply to speak, "" for a silent
    success, or None when no command matched (the caller then asks the LLM)."""
    return route(text, io or _ConfirmOnly(confirm)).reply
