"""Typing, notes, timers, reminders, small utilities and online lookups (D30 registry)."""
import json
import os
import random
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

from ultron.commands.registry import Param, command

_UTIL = "Utilities"
_ONLINE = "Online lookups"


def ask_local_ai(prompt: str) -> str:
    try:
        from ultron.brain import ask_once
        return ask_once(prompt)
    except Exception as e:
        return f"Error querying local AI: {e}"


def _say_later(seconds: float, text: str):
    def run():
        time.sleep(seconds)
        from ultron.voice.speaker import speak
        speak(text)
    threading.Thread(target=run, daemon=True, name="timer").start()


_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


# ---- dictation: checked before every other command ----
@command("type_text", "Type the dictated words at the cursor (dictation).", group="Typing",
         title="type {text}", raw=True, stages=("rule",), priority=100,
         params=[Param("text", "str", "the words to type")],
         # "write" is dictation unless a thing to compose follows: "write a note", "write tests for x.py"
         rules=[r"^\s*(?:type|insert|write(?!\s+(?:a|an|the|some|down|me|my|unit|tests?|boilerplate|template"
                r"|code|email|mail|message|reply|letter|note|pytest)\b))\b[\s,:.-]+(?P<text>.+)$"],
         examples=["type hello world", "type restart later", "write see you tomorrow", "insert my email signature"])
def type_text(text: str) -> str:
    """Words after "type" are pasted, never run: "type restart later" types it."""
    if text.endswith(".") and not text.endswith("..."):
        text = text[:-1]  # the full stop Whisper adds at the end of a sentence
    import pyautogui
    import pyperclip
    pyautogui.FAILSAFE = False
    target = _front_window()
    pyperclip.copy(text)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")
    _typed.update(chars=len(text), hwnd=target.hwnd if target else None,
                  process=target.process if target else "", title=target.title if target else "")
    return ""


# What ULTRON last typed and where, so "undo typing" can delete exactly that (D39). Not Ctrl+Z: that
# would undo whatever the app thinks the last edit was.
_typed: dict = {"chars": 0, "hwnd": None, "process": "", "title": ""}
PENDING_SECONDS = 30  # how long "Type what?" waits for the words


def _front_window():
    """The window in front, or None when it cannot be found (not Windows, no pywin32)."""
    try:
        from ultron.commands import windows
        return windows._win32().foreground()
    except Exception:
        return None


@command("start_typing", "Start dictation when no words were given: asks what to type, then types the next thing said.",
         group="Typing", title="type", stages=("rule",), priority=101,
         rules=[r"(?:start )?(?:typing|dictation|dictating)", r"type(?: something| out something| for me)?",
                r"(?:let s |let us )?(?:start|begin) (?:to )?(?:type|dictate)(?: something)?"],
         examples=["type", "type something", "start typing"])
def start_typing() -> str:
    from ultron.commands import context
    context.set_pending("type_text")
    return "Type what?"


@command("undo_typing", "Delete the words ULTRON last typed, by sending that many backspaces to the same window.",
         group="Typing", title="undo typing", priority=100,
         params=[Param("app", "str", "the app it was typed in, if the user named one", required=False)],
         rules=[r"(?:undo|remove|delete|erase|clear) (?:the |my )?(?:typing|text|that|what you (?:just )?typed|whatever you (?:just )?typed"
                r"|the (?:last )?(?:thing|words?) you typed|what you wrote)(?: (?:in|from|on) (?P<app>.+))?",
                r"(?:undo|delete|erase) (?:the )?(?:last )?(?:typing|dictation)",
                r"(?:undo|delete|erase) (?:what|whatever) you (?:just )?(?:typed|wrote)(?: (?:in|from|on) (?P<app>.+))?",
                r"(?:take back|scratch) (?:that|what you typed)"],
         examples=["undo typing", "delete that", "delete what you typed", "delete the text",
                   "undo whatever you typed in claude", "erase what you just typed", "undo the typing"],
         not_examples=["delete the file", "undo", "delete my last email", "delete the routine"])
def undo_typing(app: str | None = None) -> str:
    chars = _typed["chars"]
    if not chars:
        return "I haven't typed anything lately, so there is nothing to undo."
    front = _front_window()
    if front is None or front.hwnd != _typed["hwnd"]:
        where = (_typed["title"].split(" - ")[-1] or _typed["process"] or "that window")
        return f"I typed that in {where}, and it isn't in front now. Switch back to it and ask again. I won't guess."
    if app:
        from ultron.commands import apps, windows
        if not windows.matches(front, apps.canonical(app)):
            return f"The window in front isn't {app}. I typed in {_typed['title'] or _typed['process']}. Nothing deleted."
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.press("backspace", presses=chars, interval=0)
    _typed["chars"] = 0
    return f"Deleted the {chars} characters I typed."


# ---- screen and writing ----
def _first_line(text: str, limit: int = 90) -> str:
    line = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 2), text.strip())
    return line if len(line) <= limit else line[:limit].rsplit(" ", 1)[0] + "..."


@command("read_screen", "Read the text on the screen or the front window (OCR) and copy it to the clipboard.",
         group=_UTIL, title="read my {where}", priority=50,
         params=[Param("where", "choice", "what to read: the whole screen or just the front window",
                       required=False, choices=("screen", "window"))],
         rules=[r"(?:read|scan|ocr)(?: my| the| this)? (?P<where>screen|window)(?: text)?",
                r"scan (?:the )?(?P<where>screen) text"],
         examples=["read my screen", "scan the screen text", "copy the text on my screen",
                   "what does my screen say, copy it", "read this window", "ocr the window in front"],
         not_examples=["take a screen grab", "grab my screen", "take a screenshot"])
def read_screen(where: str = "screen") -> str:
    """Windows' own OCR (ultron.ocr), all in memory: nothing is saved to disk."""
    import pyperclip
    from ultron import ocr
    image = ocr.grab_active_window() if where == "window" else None
    image = image or ocr.grab_screen()
    try:
        text = ocr.read_text(image)
    except ocr.OcrUnavailable as e:
        return f"I can't read the screen: {e}"
    if not text:
        return f"I looked at the {where} but found no readable text."
    pyperclip.copy(text)
    lines = len([ln for ln in text.splitlines() if ln.strip()])
    return (f"Read {lines} line{'s' if lines != 1 else ''}, copied to your clipboard. "
            f"It starts: {_first_line(text)}")


@command("draft_message", "Draft an email or message with the LLM and copy it to the clipboard.", group=_UTIL,
         title="draft a message", priority=50,
         params=[Param("instruction", "str", "what the message should say", cues=("about", "saying", "to"))],
         raw=True, rules=[r"^.*\bdraft (?:an? )?(?:email|reply|message|mail)\b(?P<instruction>.*)$"],
         examples=["draft an email to my manager asking for friday off", "draft a reply saying i will be late",
                   "write an email to the landlord about the leak", "compose a message thanking the team"])
def draft_message(instruction: str = "") -> str:
    import pyperclip
    draft = ask_local_ai("Write a short, professional message body (no headers) for this request: "
                         + (instruction.strip() or "a polite reply"))
    pyperclip.copy(draft)
    return "Drafted. It's on your clipboard."


# ---- expenses, notes, calendar ----
_EXPENSES = "finances.csv"


@command("log_expense", "Log money spent, with a category, in finances.csv.", group=_UTIL,
         title="log {amount} spent on {category}",
         params=[Param("amount", "int", "amount of money"),
                 Param("category", "str", "what it was spent on", required=False, cues=("on", "for"))],
         priority=50,
         rules=[r"log (?:an expense of )?(?P<amount>\w+(?: \w+)?) (?:dollars |rupees |bucks )?(?:spent )?(?:on|for) (?P<category>.+)",
                r"log expense (?P<amount>\d+)(?: (?:on|for) (?P<category>.+))?",
                r"i spent (?P<amount>\d+)(?: rupees| dollars)? on (?P<category>.+)"],
         examples=["log 50 rupees for lunch", "log twenty dollars for dinner", "i spent 300 on groceries",
                   "log expense 120 for petrol", "add an expense of 500 for books"])
def log_expense(amount: int, category: str = "General") -> str:
    if amount <= 0:
        return "I couldn't identify the expense amount."
    category = category.capitalize()
    new = not os.path.exists(_EXPENSES)
    with open(_EXPENSES, "a", encoding="utf-8") as f:
        if new:
            f.write("Date,Amount,Category\n")
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S},{amount},{category}\n")
    return f"Logged {amount} spent on {category}."


@command("spending_summary", "Total of the logged expenses.", group=_UTIL, title="spending summary", priority=50,
         rules=[r"how much (?:did|have) i spen[dt](?: so far)?|spending summary|check (?:my )?budget"],
         examples=["how much did i spend", "spending summary", "check my budget", "what's my total spending"])
def spending_summary() -> str:
    if not os.path.exists(_EXPENSES):
        return "No expenses have been logged yet."
    total, count = 0.0, 0
    with open(_EXPENSES, encoding="utf-8") as f:
        for line in f.readlines()[1:]:
            parts = line.strip().split(",")
            try:
                total += float(parts[1])
                count += 1
            except (IndexError, ValueError):
                pass
    return f"You have spent a total of {total:g} across {count} logged items."


@command("show_calendar", "Read the next events from calendar.ics.", group=_UTIL, title="read my schedule",
         priority=50, rules=[r"(?:what s |what is )?my schedule(?: today)?|show (?:my )?calendar"],
         examples=["what is my schedule", "show calendar", "what's on my calendar", "my schedule today"])
def show_calendar() -> str:
    if not os.path.exists("calendar.ics"):
        return "There is no calendar.ics file to read. Calendar connections come later."
    with open("calendar.ics", encoding="utf-8") as f:
        events = re.findall(r"SUMMARY:(.*)", f.read())
    if not events:
        return "Your calendar is empty."
    return "Your next events: " + " ... ".join(e.strip() for e in events[:3])


_NOTES = "notes.md"


@command("write_note", "Save a note in notes.md.", group=_UTIL, title="save a note",
         params=[Param("note", "str", "the note text", cues=("note that", "note to", "note", "down that", "down"))],
         priority=55, rules=[r"(?:write|save|take|make) (?:a |down a )?note(?: that| to| saying)? (?P<note>.+)",
                             r"(?:jot|note) down (?:that )?(?P<note>.+)"],
         examples=["write a note to buy milk", "save a note that the meeting moved to 3",
                   "take a note call the bank", "jot down that the wifi password changed",
                   "add a bus stop to my notes"])
def write_note(note: str) -> str:
    with open(_NOTES, "a", encoding="utf-8") as f:
        f.write(f"- [{datetime.now():%Y-%m-%d %I:%M %p}] {note.capitalize()}\n")
    return "Saved to your notes."


@command("read_notes", "Read the last saved notes.", group=_UTIL, title="read my notes", priority=55,
         rules=[r"read (?:me )?(?:my |the )?notes|what are my notes|show (?:me )?my notes"],
         examples=["read my notes", "read notes", "what are my notes", "what did i write down"])
def read_notes() -> str:
    if not os.path.exists(_NOTES):
        return "You don't have any notes saved yet."
    with open(_NOTES, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if not lines:
        return "Your notepad is empty."
    last = [line.lstrip("- ") for line in lines[-3:]]
    return f"You have {len(lines)} notes. The last ones: " + " ... ".join(last)


# ---- timers and reminders ----
_UNIT = Param("unit", "choice", "time unit", choices=("seconds", "minutes", "hours"))


@command("set_timer", "Start a timer that speaks when it ends.", group=_UTIL, title="set a timer for {amount} {unit}",
         params=[Param("amount", "int", "how many units"), _UNIT], priority=56,
         rules=[r"(?:set |start )?(?:a )?timer for (?P<amount>\w+) (?P<unit>second|minute|hour)s?",
                r"(?:set |start )?(?:a )?(?P<amount>\w+) (?P<unit>second|minute|hour) timer"],
         examples=["set a timer for 5 minutes", "timer for 30 seconds", "start a 10 minute timer",
                   "set a timer for two hours", "count down 3 minutes for me"])
def set_timer(amount: int, unit: str) -> str:
    _say_later(amount * _UNIT_SECONDS[unit.rstrip("s")], f"Your timer for {amount} {unit} is done.")
    return f"Timer set for {amount} {unit}."


@command("set_reminder", "Remind the user of something after a number of seconds, minutes or hours.",
         group=_UTIL, title="remind you in {amount} {unit} to {task}",
         params=[Param("amount", "int", "how many units"), _UNIT,
                 Param("task", "str", "what to remind about", cues=("to",))], priority=57,
         rules=[r"remind me in (?P<amount>\w+(?: \w+)?) (?P<unit>second|minute|hour)s? to (?P<task>.+)",
                r"remind me to (?P<task>.+) in (?P<amount>\w+(?: \w+)?) (?P<unit>second|minute|hour)s?"],
         examples=["remind me in 10 minutes to check the oven", "remind me to call mom in 2 hours",
                   "in 20 minutes remind me to stretch"],
         not_examples=["remind me to go to sleep at 11", "what did i ask you to remind me"])
def set_reminder(amount: int, unit: str, task: str) -> str:
    _say_later(amount * _UNIT_SECONDS[unit.rstrip("s")], f"Reminder: {task}.")
    return f"I will remind you to {task} in {amount} {unit}."


# ---- small utilities ----
_NATO = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                 "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliett Kilo Lima Mike November "
                 "Oscar Papa Quebec Romeo Sierra Tango Uniform Victor Whiskey X-ray Yankee Zulu".split()))


@command("spell_word", "Spell a word with the NATO alphabet.", group=_UTIL, title="spell {word}",
         params=[Param("word", "str", "the word", cues=("spell",))], priority=50,
         rules=[r"(?:how do you )?spell (?:the word )?(?P<word>\w+)"],
         examples=["spell necessary", "how do you spell rhythm", "spell the word queue", "spell out bureau"])
def spell_word(word: str) -> str:
    word = word.split()[0].upper()
    return f"{word} is spelled: " + ", ".join(_NATO.get(c, c) for c in word)


@command("flip_coin", "Flip a coin.", group=_UTIL, title="flip a coin", priority=50,
         rules=[r"(?:flip|toss) a coin|heads or tails"],
         examples=["flip a coin", "toss a coin", "heads or tails", "help me decide with a coin"])
def flip_coin() -> str:
    return f"It is {random.choice(['Heads', 'Tails'])}."


@command("roll_die", "Roll a six-sided die.", group=_UTIL, title="roll a die", priority=50,
         rules=[r"roll (?:a |the )?(?:dice|die)"],
         examples=["roll a dice", "roll a die", "roll the dice", "give me a random number from one to six"])
def roll_die() -> str:
    return f"It is a {random.randint(1, 6)}."


_MATH_WORDS = (("times", "*"), ("multiplied by", "*"), ("x", "*"), ("divided by", "/"), ("over", "/"),
               ("plus", "+"), ("minus", "-"), ("point", "."))


def _math(expression: str) -> str | None:
    expr = f" {expression.lower()} "
    for word, op in _MATH_WORDS:
        expr = expr.replace(f" {word} ", f" {op} ")
    expr = expr.strip()
    if not re.fullmatch(r"[\d\s+\-*/().]+", expr) or not re.search(r"\d\s*[+\-*/]\s*\(?\s*\d", expr):
        return None
    try:
        result = eval(expr, {"__builtins__": {}}, {})  # digits and operators only, checked above
    except (SyntaxError, ZeroDivisionError, ValueError):
        return None
    return f"{result:g}" if isinstance(result, float) else str(result)


@command("calculate", "Work out a simple arithmetic expression.", group=_UTIL, title="calculate {expression}",
         params=[Param("expression", "str", "the arithmetic, for example 12 times 7",
                       cues=("calculate", "what is", "what s", "how much is"))], priority=58,
         rules=[r"(?:calculate|compute|what s|what is|how much is) (?P<expression>[\d ().]+(?: (?:times|multiplied by|x|divided by|over|plus|minus|point) [\d ().]+)+)"],
         examples=["calculate 12 times 7", "what is 45 plus 17", "how much is 100 divided by 8",
                   "what's 3 minus 9", "work out 15 times 15"])
def calculate(expression: str) -> str | None:
    result = _math(expression)
    return None if result is None else f"The answer is {result}."


@command("tell_joke", "Tell a programming joke.", group=_UTIL, title="tell a joke", priority=50,
         rules=[r"(?:tell me |say )?(?:a |another )?joke"],
         examples=["tell me a joke", "joke", "make me laugh", "say something funny", "another joke"],
         not_examples=["tell me a joke about cats", "is that a joke", "you are a joke"])
def tell_joke() -> str:
    return random.choice([
        "Why do programmers wear glasses? Because they can't C sharp.",
        "There are 10 types of people: those who understand binary, and those who don't.",
        "How many programmers does it take to change a light bulb? None, that's a hardware problem.",
        "A SQL query walks into a bar, walks up to two tables and asks: can I join you?",
    ])


# ---- online lookups ----
def _get(url: str, timeout: float = 4) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


@command("speed_test", "Measure internet latency and download speed.", group=_ONLINE, title="run a speed test",
         priority=50, rules=[r"(?:run (?:a )?|do (?:a )?)?(?:internet )?speed test|check (?:my )?internet speed"],
         examples=["run a speed test", "check my internet speed", "how fast is my internet", "is my wifi slow"])
def speed_test() -> str:
    t0 = time.time()
    try:
        _get("https://www.google.com", 3)
    except Exception:
        return "The internet check failed. You appear to be offline."
    latency = int((time.time() - t0) * 1000)
    try:
        t1 = time.time()
        size = len(_get("https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png", 5))
        mbps = size * 8 / 1e6 / (time.time() - t1)
        return f"Latency is {latency} milliseconds; a rough download speed is {mbps:.1f} megabits per second."
    except Exception:
        return f"Connected, with a latency of {latency} milliseconds."


@command("translate", "Translate text into another language with the LLM.", group=_ONLINE,
         title="translate {text} to {language}",
         params=[Param("text", "str", "the text to translate", cues=("translate",)),
                 Param("language", "str", "the target language", cues=("to", "into", "in"))], priority=50,
         rules=[r"translate (?P<text>.+) (?:to|into) (?P<language>[a-z ]+)",
                r"how do you say (?P<text>.+) in (?P<language>[a-z]+)"],
         examples=["translate good morning to spanish", "translate thank you into japanese",
                   "how do you say where is the station in german"])
def translate(text: str, language: str) -> str:
    result = ask_local_ai(f"Translate into {language}. Output only the translation:\n\n{text}")
    return f"In {language.capitalize()}: {result}"


@command("ip_address", "Say the local and public IP address.", group=_ONLINE, title="say my IP address",
         priority=50, rules=[r"(?:what s |what is )?my ip(?: address)?|ip configuration"],
         examples=["what's my ip", "my ip address", "what is my ip address", "show my ip configuration"])
def ip_address() -> str:
    import socket
    local = socket.gethostbyname(socket.gethostname())
    try:
        public = _get("https://api.ipify.org").decode().strip()
    except Exception:
        public = "unknown"
    return f"Your local IP is {local}, and your public IP is {public}."


@command("news_headlines", "Read three world headlines from BBC News.", group=_ONLINE, title="read the headlines",
         priority=50, rules=[r"(?:read )?(?:today s |the |current )?(?:news )?headlines|(?:current|latest|today s) news|what s in the news"],
         examples=["read today's headlines", "news headlines", "what's in the news", "latest news",
                   "anything happening in the world today"])
def news_headlines() -> str:
    try:
        xml = _get("https://feeds.bbci.co.uk/news/world/rss.xml").decode("utf-8")
    except Exception:
        return "I can't reach the news feed right now."
    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", xml) or re.findall(r"<title>(.*?)</title>", xml)
    return "Top world headlines: " + ". ... ".join(titles[1:4])


@command("wikipedia", "Read the Wikipedia summary of a topic.", group=_ONLINE, title="look up {topic} on Wikipedia",
         params=[Param("topic", "str", "the topic", cues=("wikipedia for", "wikipedia", "about"))], priority=50,
         rules=[r"(?:search )?wikipedia(?: for)? (?P<topic>.+)", r"(?:what does )?wikipedia (?:say )?about (?P<topic>.+)",
                r"(?:look up|search for|search) (?P<topic>.+) on wikipedia"],
         examples=["wikipedia alan turing", "search wikipedia for black holes", "what does wikipedia say about rome"])
def wikipedia(topic: str) -> str:
    try:
        data = json.loads(_get("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(topic)))
    except Exception:
        return "I couldn't reach Wikipedia right now."
    summary = data.get("extract", "No summary found.")
    return "According to Wikipedia: " + (summary[:250] + "..." if len(summary) > 250 else summary)


@command("weather", "Say the current temperature where the user is (by IP location).", group=_ONLINE,
         title="say the weather", priority=50,
         rules=[r"(?:what s |what is |how s |how is )?(?:the )?weather(?: like)?(?: today| now| outside)?|is it (?:hot|cold) outside"],
         examples=["what's the weather", "weather", "how's the weather today", "is it cold outside",
                   "do i need a jacket today", "what's the temperature outside"],
         not_examples=["what is the weather like on mars", "weather the storm"])
def weather() -> str:
    try:
        loc = json.loads(_get("http://ip-api.com/json"))
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={loc.get('lat', 0)}"
               f"&longitude={loc.get('lon', 0)}&current_weather=true")
        temp = json.loads(_get(url))["current_weather"]["temperature"]
    except Exception:
        return "I can't reach the weather service right now."
    return f"In {loc.get('city', 'your area')}, it is {temp} degrees Celsius."
