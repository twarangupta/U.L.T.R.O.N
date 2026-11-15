"""System commands: apps, websites, folders, search, media, volume, power status, screenshots.

Windows only (D22). Each command is declared once for all three stages (D30).
"""
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime

import psutil

from commands import apps
from commands.registry import Done, Param, command

try:
    import ctypes
except ImportError:  # pragma: no cover
    ctypes = None

_APPS = "Windows and apps"
_MEDIA = "Media and volume"
_PC = "PC status"

# ---- helpers ----
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2


def press_media_key(vk_code: int):
    if sys.platform == "win32" and ctypes:
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # key up


CHROME_PATHS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]


def open_browser(url: str | None = None) -> bool:
    for path in CHROME_PATHS:
        if os.path.exists(path):
            subprocess.Popen([path, url] if url else [path])
            return True
    import webbrowser
    webbrowser.open(url or "https://www.google.com")
    return True


def _endpoint(device=None):
    """The Windows speaker volume control (pycaw).

    New pycaw returns a wrapper whose EndpointVolume is ready to use; old pycaw returns the
    raw device, which needs Activate. Both work here; device is for tests.
    """
    if device is None:
        from pycaw.pycaw import AudioUtilities
        device = AudioUtilities.GetSpeakers()
    volume = getattr(device, "EndpointVolume", None)
    if volume is not None:
        return volume
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume
    interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))


def _set_mute(on: bool):
    _endpoint().SetMute(1 if on else 0, None)


# ---- search, websites, apps, folders ----
_ENGINE_LEFTOVER = re.compile(r"^(?:(?:on|in|with|using) )?(?:google|the web|the internet|online|bing)(?: for)? ", re.I)
_ENGINE_FOR = re.compile(r"^(?:google|the web|the internet|online|bing) for ", re.I)


def clean_query(query: str) -> str:
    """Drop the search engine the sentence named: "google for new cars" -> "new cars".

    "search google maps for a cafe" is untouched: only "<engine> for ...", "on google ..." and
    "the web ..." at the start are leftovers of the cue words.
    """
    out = query.strip()
    for _ in range(2):
        m = _ENGINE_LEFTOVER.match(out)
        if m and (out[:m.end()].lower().startswith(("on ", "in ", "with ", "using ", "the ")) or _ENGINE_FOR.match(out)):
            out = out[m.end():].strip()
    out = re.sub(r"\s+(?:on google|on the web|online)$", "", out, flags=re.I).strip()
    return out or query.strip()


@command("web_search", "Search Google in the browser.", group=_APPS, title="search Google for {query}",
         params=[Param("query", "str", "what to search for",
                       cues=("search for", "google for", "search the web for", "look up", "search", "google"))],
         rules=[r"(?:search|google)(?: the web| online)?(?: for)? (?P<query>.+)",
                r"look up (?P<query>.+?)(?: online| on google)?",
                # "open google chrome and search for X": the search is the point, so it wins over open_app
                r"(?:open|launch|start|go to)(?: up)? (?:google chrome|chrome|the browser|my browser|google|edge)"
                r"(?:,? and| then|,)? (?:search|google|look up)(?: for)? (?P<query>.+)"], priority=40,
         examples=["search for python decorators", "google the weather in delhi", "look up cheap flights to goa",
                   "search the web for pasta recipes", "find me something online about black holes",
                   "google how to boil an egg"],
         not_examples=["search my files", "search the codebase", "can you search a file for me in my pc"])
def web_search(query: str) -> str:
    query = clean_query(query)
    open_browser(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
    return Done(f"Searching Google for {query}.")


SITES = {"gmail": "https://gmail.com", "youtube": "https://youtube.com", "google": "https://google.com",
         "github": "https://github.com", "reddit": "https://reddit.com",
         "stackoverflow": "https://stackoverflow.com", "linkedin": "https://linkedin.com",
         "chatgpt": "https://chatgpt.com", "netflix": "https://netflix.com", "amazon": "https://amazon.in"}


@command("open_website", "Open a well-known website in the browser.", group=_APPS, title="open {site}",
         params=[Param("site", "choice", "the website", choices=tuple(SITES))],
         rules=[r"(?:open|launch|go to|start|pull up)(?: up)? (?:the )?(?P<site>" + "|".join(SITES)
                + r")(?: website| site| dot com| com)?"], priority=48,
         examples=["open youtube", "go to gmail", "open github", "launch reddit", "pull up stackoverflow",
                   "take me to youtube", "open my gmail", "show me linkedin"])
def open_website(site: str) -> str:
    open_browser(SITES[site])
    return Done(f"Opening {site.capitalize()}.")


def _launch(app: str) -> str | None:
    if app in ("chrome", "google chrome"):
        open_browser()
        return "Google Chrome"
    if app in ("vs code", "vscode", "visual studio code", "code"):
        subprocess.Popen("code", shell=True)
        return "Visual Studio Code"
    if app == "spotify":
        subprocess.Popen("start spotify:", shell=True)
        return "Spotify"
    if app == "calculator":
        subprocess.Popen("calc")
        return "Calculator"
    if app == "notepad":
        subprocess.Popen("notepad")
        return "Notepad"
    if app in ("file explorer", "explorer", "files"):
        subprocess.Popen("explorer")
        return "File Explorer"
    if app in ("docker", "docker desktop"):
        path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
        subprocess.Popen([path] if os.path.exists(path) else "Docker Desktop.exe", shell=not os.path.exists(path))
        return "Docker Desktop"
    if app in ("task manager",):
        subprocess.Popen("taskmgr")
        return "Task Manager"
    found = apps.find_installed(app)
    if found:
        if found[1].startswith(apps.APPS_FOLDER):
            subprocess.Popen(["explorer.exe", found[1]])  # Store / MSIX apps such as Claude
        else:
            os.startfile(found[1])
        return apps.pretty(found[0])
    return None


@command("open_app", "Open (launch) an installed app.", group=_APPS, title="open {app}",
         params=[Param("app", "app", "the app to open, for example chrome, vs code, spotify, calculator",
                       cues=("open", "launch", "start", "run"))],
         doing=None, priority=35,
         rules=[r"(?:open|launch|start|run|fire up|load)(?: up)?(?: in)? (?:the |my )?(?P<app>.+?)(?: app| application| for me)?"],
         examples=["open chrome", "open google chrome", "launch spotify", "start vs code", "open the calculator",
                   "fire up notepad", "open docker desktop", "run obsidian", "can you open file explorer",
                   "open the paint app"],
         not_examples=["open the door", "open a bank account", "is the shop open today", "open up about my feelings"])
def open_app(app: str) -> str | None:
    if app in ("this", "everything"):
        return None
    name = _launch(app)
    if name is None:
        return None
    return Done(f"Opening {name}.")


FOLDERS = ("downloads", "documents", "desktop", "pictures", "music", "videos")
_JUST_MADE = re.compile(r"\b(?:just|last|previous|newly)\b.*\b(?:created|made|new)\b|\bnew folder\b|\bthe folder (?:you|i) (?:just )?(?:created|made)\b")


def folder_roots() -> list[str]:
    """Where a folder named in speech is looked for, nearest first (OneDrive copies included)."""
    home = os.path.expanduser("~")
    roots = []
    for base in (home, os.path.join(home, "OneDrive")):
        for name in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"):
            path = os.path.join(base, name)
            if os.path.isdir(path):
                roots.append(path)
    roots.append(home)
    return roots


def _recent_folders() -> list[str]:
    """Folders from the Windows Recent list (best effort, newest first)."""
    found = []
    try:
        import glob
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        recent = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Recent")
        links = sorted(glob.glob(os.path.join(recent, "*.lnk")), key=os.path.getmtime, reverse=True)[:60]
        for link in links:
            target = shell.CreateShortCut(link).Targetpath
            if target and os.path.isdir(target):
                found.append(target)
    except Exception:
        pass
    return found


def find_folder(name: str, roots: list[str] | None = None, recent: list[str] | None = None) -> str | None:
    """The folder the user named, or None. Roots and recent are for tests."""
    from commands import context
    low = " ".join(re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split())
    low = re.sub(r"^(?:the|my) ", "", low)
    low = re.sub(r" (?:folder|directory)$", "", low).strip()
    if _JUST_MADE.search(low) or low in ("new", "new folder"):
        if context.created_folder and os.path.isdir(context.created_folder):
            return context.created_folder
    standard = low if low.endswith("s") or low in ("desktop", "music") else low + "s"
    roots = folder_roots() if roots is None else roots
    for base in roots:
        if os.path.basename(base).lower() in (low, standard):
            return base
    for base in roots:  # a folder inside one of the usual places, then one level deeper
        for entry in _scan(base):
            if _same(entry, low):
                return entry
    for base in roots[:6]:
        for sub in _scan(base):
            for entry in _scan(sub):
                if _same(entry, low):
                    return entry
    for path in (_recent_folders() if recent is None else recent):
        if _same(path, low):
            return path
    return None


def _scan(base: str) -> list[str]:
    try:
        return [e.path for e in os.scandir(base) if e.is_dir() and not e.name.startswith(".")]
    except OSError:
        return []


def _same(path: str, low: str) -> bool:
    leaf = " ".join(re.sub(r"[^a-z0-9 ]+", " ", os.path.basename(path).lower()).split())
    return leaf == low


@command("open_folder", "Open a folder in File Explorer by name, or the one just created.",
         group=_APPS, title="open the {folder} folder",
         params=[Param("folder", "str", "the folder's name, for example downloads or cast, or 'the new folder'")],
         priority=47,
         rules=[r"(?:open|show|go to|reveal)(?: me)? (?:the |my )?(?P<folder>download|document|picture|video)s?(?: folder| directory)?",
                r"(?:open|show|go to|reveal)(?: me)? (?:the |my )?(?P<folder>desktop|music)(?: folder| directory)",
                r"(?:open|show|go to|reveal)(?: me)? (?P<folder>(?:the )?(?:new )?folder (?:that )?(?:you|i) (?:just )?(?:created|made))",
                r"(?:open|show|go to|reveal)(?: me)? (?:the |my )?(?P<folder>(?:new )?.+?) (?:folder|directory)"],
         examples=["open my downloads", "show me the documents folder", "open downloads folder",
                   "go to my pictures", "open the desktop folder", "where are my downloads, open them",
                   "open the invoices folder", "open the new folder you just created"],
         not_examples=["create a folder called invoices", "delete this folder"])
def open_folder(folder: str) -> str:
    path = find_folder(folder)
    if path is None:
        return f"I couldn't find a folder called {folder.strip()}."
    subprocess.Popen(["explorer", os.path.normpath(path)])
    name = os.path.basename(os.path.normpath(path)) or path
    return Done(f"Opening your {name} folder." if name.lower() in FOLDERS else f"Opening the {name} folder.")


_WHERE = r"(?: (?:on|in) (?:the |my )?(?P<location>desktop|documents|downloads|pictures|music|videos)(?: folder)?)?"
_NAMED = r"(?:,? (?:and )?(?:name it|call it|called|named|with the name) (?P<name>.+?))?"


@command("create_folder", "Create a new folder, on the Desktop unless another folder is named.", group=_APPS,
         title="create a folder {name} in {location}",
         params=[Param("name", "str", "the new folder's name", required=False,
                       cues=("name it", "call it", "called", "named")),
                 Param("location", "choice", "where to create it", required=False, choices=FOLDERS)],
         priority=58,
         rules=[rf"(?:create|make|add)(?: me)?(?: a)?(?: new)? folder (?:called|named) (?P<name>.+?){_WHERE}",
                rf"(?:create|make|add)(?: me)?(?: a)?(?: new)? folder{_WHERE}{_NAMED}"],
         examples=["create a new folder on the desktop", "make a folder called invoices", "new folder on my desktop",
                   "create a folder in documents named taxes", "make a new folder and call it photos"],
         not_examples=["open the desktop folder", "delete this folder", "where is my folder"])
def create_folder(name: str | None = None, location: str | None = None) -> str:
    folder = location or "desktop"
    folder = folder if folder.endswith("s") or folder in ("desktop", "music") else folder + "s"
    base = re.sub(r'[<>:"/\|?*]', "", (name or "New folder")).strip() or "New folder"
    parent = os.path.join(os.path.expanduser("~"), folder.capitalize())
    if name:  # a name the user chose is never changed silently
        path = os.path.join(parent, base)
        if os.path.exists(path):
            return f"A folder called {base} already exists in {folder.capitalize()}."
    else:
        path = unique_path(parent, base)  # like Windows: "New folder", then "New folder (2)"
    os.makedirs(path)
    from commands import context
    context.note_folder(path)  # "open the new folder you just created", "rename it"
    return f"Created the folder {os.path.basename(path)} in {folder.capitalize()}."


def unique_path(parent: str, name: str) -> str:
    path = os.path.join(parent, name)
    n = 2
    while os.path.exists(path):
        path = os.path.join(parent, f"{name} ({n})")
        n += 1
    return path


def inside_user_folders(path: str) -> bool:
    """True only for a path under the user's own profile (never system folders, never the profile itself)."""
    home = os.path.normcase(os.path.realpath(os.path.expanduser("~")))
    full = os.path.normcase(os.path.realpath(path))
    return full.startswith(home + os.sep) and full != home


@command("rename_item", "Rename the folder ULTRON just created. Asks for the name when none is given.",
         group=_APPS, title="rename it to {name}", priority=57, raw=True,
         params=[Param("name", "str", "the new name", required=False, cues=("rename it to", "rename to", "call it", "named"))],
         rules=[r"rename (?:it|that|this|the (?:new )?folder|the folder (?:you|i) (?:just )?(?:created|made))(?: (?:to|as))? (?P<name>.+?)[.!?]?",
                r"rename (?:it|that|this|the (?:new )?folder|the folder (?:you|i) (?:just )?(?:created|made))[.!?]?"],
         examples=["rename it", "rename it to invoices", "rename the new folder to photos", "rename that folder"],
         not_examples=["rename my files in downloads", "rename the git branch"])
def rename_item(name: str | None = None) -> str:
    from commands import context
    path = context.created_folder
    if not path or not os.path.exists(path):
        return "I haven't created anything to rename. Name the folder you mean."
    if not inside_user_folders(path):
        return "That is outside your own folders. I won't rename it."
    if not name:
        context.pending = "rename_name"
        return "What should I call it?"
    new = re.sub(r'[<>:"/\|?*]', "", name).strip().rstrip(".")
    if not new:
        return "That isn't a usable name."
    target = os.path.join(os.path.dirname(path), new)
    if os.path.exists(target):
        return f"Something called {new} already exists there."
    os.rename(path, target)
    context.note_folder(target)
    return f"Renamed it to {new}."


# ---- power and status ----
@command("lock_pc", "Lock the computer (show the sign-in screen).", group=_PC, title="lock the computer",
         priority=60, rules=[r"lock(?: (?:the|my|this))?(?: pc| computer| laptop| screen| system| workstation)?"],
         examples=["lock pc", "lock my computer", "lock the screen", "lock the laptop", "lock it up",
                   "i'm stepping away, lock the computer"],
         not_examples=["lock the door", "did i lock my car", "how do locks work"])
def lock_pc() -> str:
    os.system("rundll32.exe user32.dll,LockWorkStation")
    return Done("Locking the workstation.")


@command("system_status", "Report CPU load, RAM use and battery.", group=_PC, title="system status",
         priority=55,
         rules=[r"(?:system |status )?(?:status report|system status|telemetry)",
                r"(?:check )?how much (?:ram|memory|cpu) is (?:being )?used",
                r"(?:what s |what is )?(?:my |the )?(?:cpu|ram|memory) (?:usage|load|use)"],
         examples=["system status", "status report", "how much ram is being used", "what's my cpu usage",
                   "how busy is my computer", "check memory usage", "how much memory am i using",
                   "is my laptop struggling"],
         not_examples=["how much ram does a phone need", "what is ram", "should i buy more memory"])
def system_status() -> str:
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory().percent
    battery = psutil.sensors_battery()
    battery_str = ""
    if battery:
        battery_str = (f", and your battery is at {battery.percent} percent "
                       f"{'and charging' if battery.power_plugged else 'and discharging'}")
    return f"CPU load is at {cpu} percent, memory utilization is at {mem} percent{battery_str}."


@command("take_screenshot", "Take a screenshot, save it on the Desktop and open it.", group=_PC,
         title="take a screenshot", priority=55,
         rules=[r"(?:take |capture |grab )?(?:a |the )?(?:screenshot|screen ?shot|screen capture)(?: of (?:my |the )?screen)?",
                r"capture (?:my |the )?screen"],
         examples=["take a screenshot", "screenshot", "capture the screen", "grab a screenshot",
                   "snap my screen", "save a picture of the screen"],
         not_examples=["how do i take a screenshot on a mac", "delete my screenshots"])
def take_screenshot() -> str:
    import pyautogui
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    path = os.path.join(desktop, datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png"))
    pyautogui.screenshot().save(path)
    os.startfile(path)
    return Done("Screenshot captured and saved to your Desktop.")


@command("battery_status", "Report the battery level and time left.", group=_PC, title="battery status",
         priority=55,
         rules=[r"(?:check |what s |what is |how much )?(?:the |my )?(?:battery|power percentage)(?: level| status| left| percentage| life)?(?: is (?:left|there))?"],
         examples=["battery", "how much battery is left", "what's my battery level", "battery status",
                   "am i charging", "how long will my battery last"],
         not_examples=["what battery does a tesla use", "buy a new phone battery"])
def battery_status() -> str:
    battery = psutil.sensors_battery()
    if not battery:
        return "No battery detected."
    if battery.power_plugged:
        return f"The battery is at {battery.percent} percent and charging."
    secs = battery.secsleft
    if secs in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
        return f"The battery is at {battery.percent} percent."
    return (f"The battery is at {battery.percent} percent with {secs // 3600} hours "
            f"and {(secs % 3600) // 60} minutes remaining.")


@command("disk_space", "Report free space on the C: drive.", group=_PC, title="check disk space", priority=55,
         rules=[r"(?:check )?(?:my )?(?:storage|disk space|hard drive space|free space)(?: left)?",
                r"how much (?:storage|disk space|space) (?:is |do i have )?(?:left|free)(?: on (?:my )?(?:c|c drive|disk|laptop))?"],
         examples=["check storage", "disk space", "how much storage is left", "how much space do i have left",
                   "is my drive full", "free space on c drive"],
         not_examples=["how much space is in the universe", "buy more cloud storage"])
def disk_space() -> str:
    usage = psutil.disk_usage("C:\\")
    return (f"C: drive has {usage.free / 1024 ** 3:.1f} gigabytes free out of "
            f"{usage.total / 1024 ** 3:.1f} gigabytes total.")


_CATEGORIES = {
    "Documents": (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".csv", ".pptx", ".ppt"),
    "Images": (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico"),
    "Archives": (".zip", ".rar", ".7z", ".tar", ".gz"),
    "Installers": (".exe", ".msi"),
    "Audio": (".mp3", ".wav", ".flac", ".m4a"),
    "Video": (".mp4", ".mkv", ".avi", ".mov"),
}


@command("organize_downloads", "Sort the files in Downloads into folders by type.", group=_PC,
         title="organise my downloads", doing="Sorting your downloads into folders.", priority=55,
         rules=[r"(?:organi[sz]e|sort|tidy up|tidy|clean up) (?:my |the )?downloads?(?: folder)?"],
         examples=["organize my downloads", "tidy up my downloads folder", "sort my downloads",
                   "clean up the downloads folder", "my downloads are a mess, fix them"])
def organize_downloads() -> str:
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.exists(downloads):
        return "Downloads directory not found."
    moved = 0
    for item in os.listdir(downloads):
        path = os.path.join(downloads, item)
        if os.path.isfile(path):
            ext = os.path.splitext(item)[1].lower()
            dest = next((cat for cat, exts in _CATEGORIES.items() if ext in exts), "Others")
            os.makedirs(os.path.join(downloads, dest), exist_ok=True)
            os.rename(path, os.path.join(downloads, dest, item))
            moved += 1
    return f"Sorted {moved} files in your downloads folder."


# ---- media and volume ----
_MEDIA_WORDS = r"(?: the)?(?: music| song| track| playback| media| video)?"


@command("media_play_pause", "Play or pause the music or video that is playing.", group=_MEDIA,
         title="play or pause", priority=50,
         rules=[rf"(?:play|pause|resume|unpause){_MEDIA_WORDS}"],
         examples=["play music", "pause", "pause the song", "resume the music", "pause the video",
                   "hold the music", "continue playing"],
         not_examples=["pause tracking", "play a game with me", "play chess"])
def media_play_pause() -> str:
    press_media_key(VK_MEDIA_PLAY_PAUSE)
    return Done("Media playback toggled.")


@command("media_next", "Skip to the next track.", group=_MEDIA, title="next track", priority=50,
         rules=[r"(?:next|skip)(?: the| this)?(?: song| track)?|(?:play the )?next (?:song|track)"],
         examples=["next song", "skip this track", "next track", "skip", "play the next song", "skip this one"])
def media_next() -> str:
    press_media_key(VK_MEDIA_NEXT_TRACK)
    return Done("Playing next track.")


@command("media_previous", "Go back to the previous track.", group=_MEDIA, title="previous track", priority=50,
         rules=[r"(?:previous|last) (?:song|track)|go back a (?:song|track)|play the previous (?:song|track)"],
         examples=["previous song", "previous track", "go back a song", "play the last track again",
                   "back one song"])
def media_previous() -> str:
    press_media_key(VK_MEDIA_PREV_TRACK)
    return Done("Playing previous track.")


@command("media_stop", "Stop media playback.", group=_MEDIA, title="stop the music", priority=50,
         rules=[r"stop (?:the )?(?:music|playback|song|video)"],
         examples=["stop music", "stop the playback", "stop the song", "kill the music"])
def media_stop() -> str:
    press_media_key(VK_MEDIA_STOP)
    return Done("Playback stopped.")


_VOL = r"(?:the )?(?:volume|sound|audio)"


def _step(delta: float) -> str:
    vol = _endpoint()
    new = min(1.0, max(0.0, vol.GetMasterVolumeLevelScalar() + delta))
    vol.SetMasterVolumeLevelScalar(new, None)
    return f"Volume {'increased' if delta > 0 else 'decreased'} to {round(new * 100)} percent."


@command("volume_up", "Turn the speaker volume up by 10 percent.", group=_MEDIA, title="volume up", priority=52,
         rules=[rf"(?:turn |crank |pump )?{_VOL} up(?: a bit| a little| more)?",
                rf"(?:turn up|increase|raise|boost) {_VOL}(?: a bit| a little)?",
                r"(?:make it |a bit |a little )?louder(?: please)?"],
         examples=["volume up", "turn the volume up", "make it louder", "increase the volume", "louder",
                   "turn up the sound", "i can't hear it, turn it up", "crank it up"],
         not_examples=["speak up", "turn up the heat", "turn up the brightness"])
def volume_up() -> str:
    return _step(+0.1)


@command("volume_down", "Turn the speaker volume down by 10 percent.", group=_MEDIA, title="volume down",
         priority=52,
         rules=[rf"(?:turn ){_VOL} down(?: a bit| a little| more)?|{_VOL} down",
                rf"(?:turn down|decrease|lower|reduce) {_VOL}(?: a bit| a little)?",
                r"(?:make it |a bit |a little )?(?:quieter|softer)(?: please)?"],
         examples=["volume down", "turn the volume down", "make it quieter", "lower the volume", "softer",
                   "decrease the sound", "it's too loud", "turn it down a bit"],
         not_examples=["calm down", "turn down the brightness", "slow down"])
def volume_down() -> str:
    return _step(-0.1)


@command("volume_set", "Set the speaker volume to a percentage.", group=_MEDIA, title="set the volume to {level}",
         params=[Param("level", "int", "volume from 0 to 100")], priority=53,
         rules=[rf"(?:set |change |put )?{_VOL} (?:to |at )?(?P<level>\d+)(?: percent| %)?",
                rf"(?:set|change|put) {_VOL} (?:level )?(?:to|at) (?P<level>\d+)(?: percent| %)?"],
         examples=["set the volume to 40", "volume 70 percent", "put the sound at 20", "volume to 100",
                   "change the volume to 35 percent", "make the volume fifty"],
         not_examples=["what is the volume of a sphere", "turn the volume up"])
def volume_set(level: int) -> str:
    level = max(0, min(100, level))
    _endpoint().SetMasterVolumeLevelScalar(level / 100.0, None)
    return f"Volume set to {level} percent."


@command("mute", "Mute the speakers.", group=_MEDIA, title="mute", priority=52,
         rules=[rf"mute(?: {_VOL}| the speakers| it| everything| my laptop| the pc)?|silence {_VOL}"],
         examples=["mute", "mute the sound", "mute the volume", "silence the audio", "kill the sound",
                   "turn the sound off"],
         not_examples=["unmute", "mute my microphone in zoom"])
def mute() -> str:
    _set_mute(True)
    return Done("Audio muted.")


@command("unmute", "Unmute the speakers.", group=_MEDIA, title="unmute", priority=53,
         rules=[rf"unmute(?: {_VOL}| the speakers| it| everything)?|turn {_VOL} (?:back )?on"],
         examples=["unmute", "unmute the sound", "turn the sound back on", "bring the audio back",
                   "sound on"])
def unmute() -> str:
    _set_mute(False)
    return Done("Audio unmuted.")


@command("meeting_mode", "Meeting or focus mode: mute the speakers and minimise every window.", group=_MEDIA,
         title="meeting mode", priority=55,
         rules=[r"(?:turn on |start |enable |activate )?(?:meeting|focus)(?: mode)?"],
         examples=["meeting mode", "focus mode", "start focus mode", "i have a meeting, get things quiet",
                   "activate meeting mode"])
def meeting_mode() -> str:
    import pyautogui
    _set_mute(True)
    pyautogui.hotkey("win", "m")
    return "Meeting mode activated. Master audio muted and windows minimized."
