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
_STRIP = re.compile(r"^(?:the|my|this|that) (?=\w)|(?: app| application| window| windows| browser| program| again)$")
FUZZY_MIN = 85


def clean(name: str) -> str:
    name = re.sub(r"[^a-z0-9+ ]+", " ", name.lower())
    name = " ".join(name.split())
    if name.endswith(" again"):
        name = name[:-6]
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
    """A known app, "this" or "everything", or an installed app (possibly after trimming extra words)."""
    return resolve_name(name) is not None


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


APPS_FOLDER = "shell:AppsFolder\\"


def _store_apps() -> dict[str, str]:
    """Apps without a Start Menu shortcut (Store and MSIX apps such as Claude): name -> shell:AppsFolder id."""
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        folder = win32com.client.Dispatch("Shell.Application").NameSpace("shell:AppsFolder")
        return {item.Name.lower(): APPS_FOLDER + item.Path for item in folder.Items()}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def start_menu_index() -> dict[str, str]:
    """App name (lowercase) -> .lnk path or shell:AppsFolder id. Built once."""
    index: dict[str, str] = {}
    for base in _start_menu_dirs():
        for folder, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith(".lnk"):
                    name = f[:-4].lower()
                    if "uninstall" not in name:
                        index.setdefault(name, os.path.join(folder, f))
    for name, target in _store_apps().items():
        if "uninstall" not in name:
            index.setdefault(name, target)
    return index


def skeleton(word: str) -> str:
    """Consonants only, repeats merged: "clod", "cloud" and "claude" all give "cld".

    Whisper often gets the vowels of an app name wrong but keeps its consonants.
    """
    out = ""
    for ch in re.sub(r"[^a-z]", "", word.lower()):
        if ch in "aeiouyhw":
            continue
        if not out or out[-1] != ch:
            out += ch
    return out


def find_installed(name: str, sound_alike: bool = True) -> tuple[str, str] | None:
    """(app name, path) for an installed app, by exact, fuzzy or sound-alike name, or None."""
    index = start_menu_index()
    name = clean(name)
    if name in index:
        return name, index[name]
    if len(name) < 4:
        return None
    from rapidfuzz import fuzz, process
    # Whole-name similarity only: WRatio matched partial words ("over" in a shortcut name).
    hit = process.extractOne(name, list(index), scorer=fuzz.ratio, score_cutoff=85)
    if hit:
        return hit[0], index[hit[0]]
    key = skeleton(name)
    if sound_alike and len(key) >= 3 and " " not in name:
        same = [n for n in index if " " not in n and skeleton(n) == key]
        if len(same) == 1:  # only when the sound-alike is unambiguous
            return same[0], index[same[0]]
    return None


def resolve_name(name: str, sound_alike: bool = False) -> str | None:
    """The app a spoken phrase names, trimming extra words: "clod the application by anthropic" -> "clod".

    sound_alike (opening apps only): accept a consonant match such as "clod" for Claude.
    "this" or "everything" count only as the whole phrase ("open the window, it is hot" is no app).
    """
    words = clean(name).split()
    for n in range(len(words), 0, -1):
        candidate = " ".join(words[:n])
        key = canonical(candidate)
        if key in ("this", "everything"):
            if n == len(words):
                return candidate
            continue
        if key in APP_ALIASES or find_installed(key, sound_alike) is not None:
            return candidate
    return None


def warm():
    """Build the Start Menu index in the background at startup (it takes about 0.75 s, so the first
    "open <app>" would otherwise pay for it)."""
    import threading
    threading.Thread(target=start_menu_index, daemon=True, name="app-index").start()


_ACTION_WORDS = ("minimize", "maximize", "restore", "switch to", "close", "open", "screenshot")


def hotword_names(limit: int = 24) -> list[str]:
    """Words Whisper should expect: the app names ULTRON knows (aliases first, then installed apps) and
    the window verbs. Fed to faster-whisper's hotwords so "VS Code" stops coming out as "via scroll"."""
    names = [pretty(a) for a in APP_ALIASES if len(a) >= 3]  # all of them: the names ULTRON can act on
    try:
        installed = sorted((n for n in start_menu_index() if n.isascii() and 3 <= len(n) <= 18), key=len)
    except Exception:
        installed = []
    extra = [pretty(n) for n in installed if pretty(n) not in names][:limit]  # a few of the shortest installed names
    return list(_ACTION_WORDS) + names + extra
