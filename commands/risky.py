"""Commands that can lose work or data.

Each one matches only when the whole (normalized) utterance is one of its
phrases, and only runs after the user says "confirm". So "restart the dev
server" or "remind me to empty the trash" never reboot or delete anything.
"""
import os
import re
import shutil
import sys
from dataclasses import dataclass
from typing import Callable

try:
    import ctypes
except ImportError:  # pragma: no cover
    ctypes = None


def shutdown_pc() -> str:
    if sys.platform == "win32":
        os.system("shutdown /s /t 5")
    elif sys.platform == "darwin":
        os.system("osascript -e 'tell app \"System Events\" to shut down'")
    else:
        os.system("shutdown -h +0")
    return "Shutting down in 5 seconds. Goodbye."


def restart_pc() -> str:
    if sys.platform == "win32":
        os.system("shutdown /r /t 5")
    elif sys.platform == "darwin":
        os.system("osascript -e 'tell app \"System Events\" to restart'")
    else:
        os.system("shutdown -r +0")
    return "Restarting in 5 seconds."


def _clear_folder(path: str) -> None:
    if not os.path.isdir(path):
        return
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.unlink(item_path)


def empty_recycle_bin() -> str:
    try:
        if sys.platform == "win32" and ctypes:
            SHERB_NOCONFIRMATION = 0x00000001
            SHERB_NOSOUND = 0x00000004
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOSOUND)
        elif sys.platform == "darwin":
            _clear_folder(os.path.expanduser("~/.Trash"))
        else:
            _clear_folder(os.path.expanduser("~/.local/share/Trash/files"))
            _clear_folder(os.path.expanduser("~/.local/share/Trash/info"))
        return "Recycle bin emptied."
    except Exception as e:
        return f"Failed to empty recycle bin. Error: {e}"


@dataclass(frozen=True)
class RiskyCommand:
    name: str
    pattern: re.Pattern
    action: str  # finishes the sentence "Say confirm to ..."
    run: Callable[[], str]


_DEVICE = r"(?: (?:my|the|this) (?:computer|pc|laptop|system))?"

RISKY_COMMANDS = [
    RiskyCommand(
        "shutdown",
        re.compile(rf"(?:shutdown|shut down|power off){_DEVICE}"),
        "shut down the computer",
        shutdown_pc,
    ),
    RiskyCommand(
        "restart",
        re.compile(rf"(?:restart|reboot){_DEVICE}"),
        "restart the computer",
        restart_pc,
    ),
    RiskyCommand(
        "empty recycle bin",
        re.compile(r"(?:empty|clear|clean) (?:the |my )?(?:recycle bin|trash)"),
        "empty the recycle bin",
        empty_recycle_bin,
    ),
]


def match_risky(normalized: str) -> RiskyCommand | None:
    """Return the risky command whose phrase is the entire utterance, if any."""
    for cmd in RISKY_COMMANDS:
        if cmd.pattern.fullmatch(normalized):
            return cmd
    return None
