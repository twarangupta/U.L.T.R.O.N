"""App names: the alias table, fuzzy matching and the Start Menu index.

Used to fill the app parameter ("close google chrome", "open vs cod") and to
launch apps that have no special launcher ("open obsidian" finds its Start
Menu shortcut).
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

# Spoken name -> process names (lowercase, without .exe)
APP_ALIASES: dict[str, tuple[str, ...]] = {
    "chrome": ("chrome",), "google chrome": ("chrome",), "google": ("chrome",),
    "edge": ("msedge",), "microsoft edge": ("msedge",),
    "firefox": ("firefox",), "brave": ("brave",), "opera": ("opera",),
    "vs code": ("code",), "vscode": ("code",), "visual studio code": ("code",), "code": ("code",),
    "visual studio": ("devenv",),
    "notepad": ("notepad",), "notepad plus plus": ("notepad++",),
    "file explorer": ("explorer",), "explorer": ("explorer",), "files": ("explorer",),
    "word": ("winword",), "excel": ("excel",), "powerpoint": ("powerpnt",), "outlook": ("outlook", "olk"),
    "teams": ("ms-teams", "teams"), "spotify": ("spotify",), "discord": ("discord",),
    "whatsapp": ("whatsapp",), "telegram": ("telegram",), "zoom": ("zoom",), "slack": ("slack",),
    "vlc": ("vlc",), "steam": ("steam",), "obs": ("obs64", "obs"),
    "terminal": ("windowsterminal",), "task manager": ("taskmgr",), "settings": ("systemsettings",),
    "calculator": ("calculatorapp", "calculator"), "paint": ("mspaint",),
    "postman": ("postman",), "figma": ("figma",), "notion": ("notion",), "obsidian": ("obsidian",),
    "pycharm": ("pycharm64",), "intellij": ("idea64",), "android studio": ("studio64",),
    "docker": ("docker desktop",), "docker desktop": ("docker desktop",),
}
THIS = {"it", "this", "that", "this window", "the window", "window", "current window", "this app", "this one"}
EVERYTHING = {"everything", "all", "all windows", "all apps", "every window", "all the windows", "all my windows"}
_STRIP = re.compile(r"^(?:the|my|this|that) (?=\w)|(?: app| application| window| windows| browser| program)$")
FUZZY_MIN = 85


def clean(name: str) -> str:
    name = re.sub(r"[^a-z0-9+ ]+", " ", name.lower())
    name = " ".join(name.split())
    if name in THIS or name in EVERYTHING:
        return name
    for _ in range(2):
        name = _STRIP.sub("", name).strip()
    return name


def canonical(name: str) -> str:
    """The alias-table key for a spoken app name, or the cleaned name if unknown."""
    name = clean(name)
    if name in THIS:
        return "this"
    if name in EVERYTHING:
        return "everything"
    if name in APP_ALIASES:
        return name
    best = fuzzy(name, list(APP_ALIASES))
    return best or name


def fuzzy(name: str, choices: list[str], minimum: int = FUZZY_MIN) -> str | None:
    if len(name) < 3 or not choices:
        return None
    from rapidfuzz import fuzz, process
    hit = process.extractOne(name, choices, scorer=fuzz.ratio, score_cutoff=minimum)
    return hit[0] if hit else None


def is_known(name: str) -> bool:
    return canonical(name) in APP_ALIASES


def resolvable(name: str) -> bool:
    """A known app, "this" or "everything", or an installed app's Start Menu name."""
    key = canonical(name)
    return key in APP_ALIASES or key in ("this", "everything") or find_installed(key) is not None


def find_in_text(text: str) -> str | None:
    """The app named somewhere in a sentence (longest alias first), for the matcher."""
    words = f" {clean(text)} "
    for alias in sorted(APP_ALIASES, key=len, reverse=True):
        if f" {alias} " in words:
            return alias
    for phrase in sorted(THIS | EVERYTHING, key=len, reverse=True):
        if f" {phrase} " in words:
            return "this" if phrase in THIS else "everything"
    return None


def pretty(app: str) -> str:
    return " ".join(w.upper() if w in {"vs", "vlc", "obs", "ip"} else w.capitalize() for w in app.split())


# ---- Start Menu index, for "open <any installed app>" ----
def _start_menu_dirs() -> list[str]:
    dirs = []
    for root in (os.getenv("PROGRAMDATA"), os.getenv("APPDATA")):
        if root:
            dirs.append(os.path.join(root, "Microsoft", "Windows", "Start Menu", "Programs"))
    return dirs


@lru_cache(maxsize=1)
def start_menu_index() -> dict[str, str]:
    """Shortcut name (lowercase) -> .lnk path. Built once, about 20 ms."""
    index: dict[str, str] = {}
    for base in _start_menu_dirs():
        for folder, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith(".lnk"):
                    name = f[:-4].lower()
                    if "uninstall" not in name:
                        index.setdefault(name, os.path.join(folder, f))
    return index


def find_installed(name: str) -> tuple[str, str] | None:
    """(shortcut name, path) for an installed app, by fuzzy name, or None."""
    index = start_menu_index()
    name = clean(name)
    if name in index:
        return name, index[name]
    if len(name) < 3:
        return None
    from rapidfuzz import fuzz, process
    if len(name) < 4:
        return None
    # Whole-name similarity only: WRatio matched partial words ("over" in a shortcut name).
    hit = process.extractOne(name, list(index), scorer=fuzz.ratio, score_cutoff=85)
    return (hit[0], index[hit[0]]) if hit else None
