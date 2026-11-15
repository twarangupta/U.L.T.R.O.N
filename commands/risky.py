"""Commands that can lose work or data.

All are risk "confirm": whichever stage picks them (rule, meaning matcher or
the LLM), they run only after the user says "confirm". Rules match only the
whole sentence, and near misses ("restart the dev server", "remind me to
empty the trash") are declared as not_examples for the matcher.
"""
import os
import shutil
import sys

from commands.registry import command, commands

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


_DEVICE = r"(?: (?:my|the|this) (?:computer|pc|laptop|system|machine))?"
_POWER_NOT = ["restart the dev server", "restart the server", "restart the app", "reboot the router",
              "restart the game", "shut down the server", "how do i shut down a mac", "restart later"]


@command("shutdown_pc", "Shut down the computer.", risk="confirm", confirm_text="shut down the computer",
         title="shut down the computer", group="Power", priority=70,
         rules=[rf"(?:shutdown|shut down|power off|turn off){_DEVICE}"],
         examples=["shut down", "shutdown my computer", "power off the pc", "turn off my laptop",
                   "switch off the computer", "shut the laptop down", "power down the system"],
         not_examples=_POWER_NOT)
def shutdown() -> str:
    return shutdown_pc()


@command("restart_pc", "Restart the computer.", risk="confirm", confirm_text="restart the computer",
         title="restart the computer", group="Power", priority=70,
         rules=[rf"(?:restart|reboot){_DEVICE}"],
         examples=["restart", "restart my computer", "reboot the pc", "reboot my laptop",
                   "restart the system", "give the computer a reboot", "reboot the machine"],
         not_examples=_POWER_NOT)
def restart() -> str:
    return restart_pc()


@command("empty_recycle_bin", "Permanently delete everything in the recycle bin.", risk="confirm",
         confirm_text="empty the recycle bin", title="empty the recycle bin", group="Power", priority=70,
         rules=[r"(?:empty|clear|clean) (?:out )?(?:the |my )?(?:recycle bin|trash|bin)"],
         examples=["empty the recycle bin", "clear my trash", "empty trash", "clean out the recycle bin",
                   "delete everything in the bin", "wipe the recycle bin"],
         not_examples=["remind me to empty the trash", "take out the trash", "what is in the recycle bin"])
def recycle_bin() -> str:
    return empty_recycle_bin()


def match_risky(normalized: str):
    """The risky command whose rule is the whole utterance, if any (for follow-ups)."""
    for cmd in commands("rule"):
        if cmd.risk == "confirm" and any(r.fullmatch(normalized) for r in cmd.rules):
            return cmd
    return None
