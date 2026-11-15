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


def _endpoint():
    """The Windows speaker volume control (pycaw)."""
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    interface = AudioUtilities.GetSpeakers().Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))


def _set_mute(on: bool):
    _endpoint().SetMute(1 if on else 0, None)


# ---- search, websites, apps, folders ----
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


@command("open_folder", "Open one of the user's folders in File Explorer.", group=_APPS, title="open my {folder} folder",
         params=[Param("folder", "choice", "the folder", choices=FOLDERS)], priority=47,
         rules=[r"(?:open|show|go to|reveal)(?: me)? (?:the |my )?(?P<folder>download|document|picture|video)s?(?: folder| directory)?",
                r"(?:open|show|go to|reveal)(?: me)? (?:the |my )?(?P<folder>desktop|music)(?: folder| directory)"],
         examples=["open my downloads", "show me the documents folder", "open downloads folder",
                   "go to my pictures", "open the desktop folder", "where are my downloads, open them"])
def open_folder(folder: str) -> str:
    folder = folder if folder.endswith("s") or folder in ("desktop", "music") else folder + "s"
    name = folder.capitalize()
    path = os.path.join(os.path.expanduser("~"), name)
    if not os.path.exists(path):
        return f"I couldn't locate your {name} folder."
    subprocess.Popen(["explorer", os.path.normpath(path)])
    return Done(f"Opening your {name} folder.")


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
    name = re.sub(r'[<>:"/\\|?*]', "", (name or "New folder")).strip() or "New folder"
    path = os.path.join(os.path.expanduser("~"), folder.capitalize(), name)
    if os.path.exists(path):
        return f"A folder called {name} already exists in {folder.capitalize()}."
    os.makedirs(path)
    return f"Created the folder {name} in {folder.capitalize()}."


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
