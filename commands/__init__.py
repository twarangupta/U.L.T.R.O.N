from typing import Callable

import persona
from commands.text import normalize
from commands.risky import match_risky
from commands.system import execute_system_command
from commands.git_helpers import execute_git_command
from commands.developer import execute_developer_command
from commands.general import execute_general_command, execute_typing_command

# Asks the user a yes/no question by voice. Gets the spoken prompt,
# returns True only if the user said "confirm".
ConfirmFn = Callable[[str], bool]


def execute_command(text: str, confirm: ConfirmFn | None = None) -> str | None:
    """Route a transcript to a built-in command.

    Order: dictation first, then risky commands (whole phrase plus spoken
    confirmation), then system, git, developer and general commands.
    Returns the reply to speak, "" for a silent success, or None when no
    command matched (the caller then asks the LLM).
    """
    # 1. Dictation. "type restart later" types the words, never runs them.
    response = execute_typing_command(text)
    if response is not None:
        return response

    # 2. Risky commands: only an exact phrase, and only after "confirm".
    risky = match_risky(normalize(text))
    if risky is not None:
        if confirm is None or not confirm(persona.pick(persona.CONFIRM_PROMPTS, action=risky.action)):
            return persona.pick(persona.CANCELLED_REPLIES)
        return risky.run()

    clean_text = text.strip().lower()
    for handler in (execute_system_command, execute_git_command, execute_developer_command):
        response = handler(clean_text)
        if response is not None:
            return response

    return execute_general_command(clean_text, text)
