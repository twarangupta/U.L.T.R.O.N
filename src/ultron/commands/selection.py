"""Commands about whatever text is highlighted on screen (D37).

    "explain this"            "translate this to hindi"       "summarise this"
    "make this more polite"   "reply to this"                 "what does this mean"

How it works: press Ctrl+C in the app in front, read the clipboard, put the user's own
clipboard text back, then let the local model work on the text. Short results are spoken.
A rewrite or a reply is never pasted without a spoken "confirm"; if you do not confirm, it
waits on your clipboard instead.

Limits, said honestly in the replies: Ctrl+C is never sent to a terminal (it would stop the
running program); the clipboard is restored as text only (a copied picture is not brought
back); an app that blocks copying, or a read-only page that ignores paste, cannot be helped.
"""
from __future__ import annotations

import ctypes
import re
import time
from ctypes import wintypes

from ultron.commands.registry import Param, command

_GROUP = "Selection"
_THIS = (r"(?:this|that|these|those|it|the selection|the selected (?:text|part|paragraph|sentence|words)"
         r"|the highlighted (?:text|part|paragraph|sentence|words)|what i (?:selected|highlighted))")

TERMINALS = {"cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe", "conhost.exe",
             "bash.exe", "mintty.exe", "alacritty.exe", "wezterm-gui.exe", "openconsole.exe"}
READ_LIMIT = 4000       # characters handed to the model to explain, translate or summarise
REWRITE_LIMIT = 2500    # a rewrite longer than this could be cut short by the model: refuse instead
SPOKEN_CHARS = 320      # how much of a rewrite is read aloud before asking to paste it

NOTHING_SELECTED = "I don't see anything selected. Highlight some text first, then ask again."
MODEL_SILENT = "My local model didn't answer. Check that Ollama is running."


# ---- clipboard and keys (the only parts that touch the real desktop) ----
def _clip_get() -> str:
    import pyperclip
    try:
        return pyperclip.paste()
    except Exception:
        return ""


def _clip_set(text: str):
    import pyperclip
    pyperclip.copy(text)


def _press(*keys: str):
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.hotkey(*keys)


def foreground_program() -> str:
    """Executable name of the window in front, lower case ("" if unknown)."""
    try:
        import psutil
        user32 = ctypes.windll.user32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""


def grab_selection(wait: float = 0.7) -> str | None:
    """The highlighted text, or "" if nothing is selected, or None if Ctrl+C would be unsafe here.

    A unique marker goes onto the clipboard first, so a selection that equals the old
    clipboard text is still noticed and "nothing selected" is not mistaken for it.
    """
    if foreground_program() in TERMINALS:
        return None
    old = _clip_get()
    marker = f"​ultron-probe-{time.time_ns()}"
    _clip_set(marker)
    try:
        _press("ctrl", "c")
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            time.sleep(0.05)
            got = _clip_get()
            if got != marker:
                return got.strip()
        return ""
    finally:
        _clip_set(old)


def paste_over_selection(text: str):
    """Paste text where the selection is, then bring the user's clipboard back."""
    old = _clip_get()
    _clip_set(text)
    time.sleep(0.1)
    _press("ctrl", "v")
    time.sleep(0.4)  # the app reads the clipboard asynchronously
    _clip_set(old)


def _ask(prompt: str, max_tokens: int = 200) -> str:
    from ultron.brain import ask_once
    return clean_model_text(ask_once(prompt, max_tokens=max_tokens))


def clean_model_text(text: str) -> str:
    """Plain words for the voice: no markdown marks, no wrapping quotes."""
    text = re.sub(r"[*_`#>]+", "", text or "").strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def _selected(limit: int, cut: bool = False) -> tuple[str | None, str | None]:
    """(text, None) or (None, the reply to give instead). Too long: cut at the limit, or refused."""
    text = grab_selection()
    if text is None:
        return None, ("That's a terminal, and Ctrl+C there would stop whatever is running. "
                      "I won't risk it. Copy the text yourself and ask again.")
    if not text:
        return None, NOTHING_SELECTED
    if len(text) > limit:
        if cut:
            return text[:limit], None
        return None, f"That's {len(text)} characters, too long for me to handle well. Select a paragraph or two."
    return text, None


# ---- commands that answer in words ----
@command("explain_selection", "Explain the text the user has highlighted, in plain words.", group=_GROUP,
         title="explain the selected text", priority=62,
         rules=[rf"(?:explain|clarify|decode|break down|help me understand)(?: to me| for me)? {_THIS}(?: to me| for me| simply| in simple words)?",
                rf"what (?:does|do) {_THIS} (?:mean|say|do|stand for)",
                rf"(?:tell me )?what(?: is|s)? {_THIS} (?:about|saying|trying to say)",
                rf"i don t (?:get|understand) {_THIS}"],
         examples=["explain this", "what does this mean", "explain the selected text", "can you explain what i highlighted",
                   "i don't understand this", "what does this say", "break this down for me", "what is this saying",
                   "help me understand this"],
         not_examples=["explain how a car engine works", "what does git push do", "what does this window do",
                       "explain the exception", "explain this error", "explain the stack trace",
                       "explain quantum physics", "what is the meaning of life"])
def explain_selection() -> str:
    text, problem = _selected(READ_LIMIT, cut=True)
    if problem:
        return problem
    answer = _ask("Explain what this text means in plain words, in at most three short sentences. "
                  f"Reply with the explanation only.\n\nText:\n{text}")
    return answer or MODEL_SILENT


@command("summarise_selection", "Summarise the text the user has highlighted in a sentence or two.", group=_GROUP,
         title="summarise the selected text", priority=62,
         rules=[rf"(?:summari[sz]e|sum up|recap|shorten|tldr|tl dr)(?: for me| to me)? {_THIS}(?: for me| briefly| in a (?:line|sentence))?",
                rf"(?:give me |what s )?(?:the |a )?(?:gist|summary|tldr|tl dr|short version) (?:of )?{_THIS}",
                rf"what s {_THIS} (?:in short|in brief)"],
         examples=["summarise this", "summarize the selected text", "tldr this", "give me the gist of this",
                   "sum this up", "give me a summary of what i highlighted", "what's the short version of this"],
         not_examples=["summarise my day", "summarise yesterday", "recap my day", "summarise the news"])
def summarise_selection() -> str:
    text, problem = _selected(READ_LIMIT, cut=True)
    if problem:
        return problem
    answer = _ask("Summarise this text in at most two short sentences. Reply with the summary only.\n\n"
                  f"Text:\n{text}")
    return answer or MODEL_SILENT


def is_latin(text: str) -> bool:
    """True if the letters are Latin script, which the English voice can read aloud."""
    letters = [c for c in text if c.isalpha()]
    return not letters or sum(c.isascii() or "À" <= c <= "ɏ" for c in letters) / len(letters) > 0.9


@command("translate_selection", "Translate the text the user has highlighted into a language.", group=_GROUP,
         title="translate the selected text to {language}", priority=63,
         params=[Param("language", "str", "the target language, for example Hindi", cues=("to", "into", "in"))],
         rules=[rf"translate {_THIS}(?: text| sentence| paragraph)? (?:to|into|in) (?P<language>[a-z]+(?: [a-z]+)?)",
                rf"(?:say|write) {_THIS} in (?P<language>[a-z]+)",
                rf"what is {_THIS} in (?P<language>[a-z]+)",
                rf"(?:translate|convert) {_THIS}(?: text)? (?:to|into|in) (?P<language>[a-z]+)"],
         examples=["translate this to hindi", "translate the selected text into french", "translate this into spanish",
                   "say this in german", "what is this in japanese", "can you translate what i highlighted to tamil",
                   "convert this to bengali"],
         not_examples=["translate good morning to spanish", "how do you say thank you in french",
                       "what is hello in german"])
def translate_selection(language: str) -> str:
    text, problem = _selected(READ_LIMIT, cut=True)
    if problem:
        return problem
    language = language.strip().capitalize()
    result = _ask(f"Translate this text into {language}. Output only the translation.\n\n{text}",
                  max_tokens=min(1024, len(text) // 2 + 150))
    if not result:
        return MODEL_SILENT
    if is_latin(result):
        return f"In {language}: {result}"
    _clip_set(result)  # the English voice cannot read other scripts aloud
    return f"Translated to {language}. I can't read that script aloud, so it's on your clipboard."


# ---- commands that offer to paste ----
def _offer_to_paste(result: str, ask: str) -> str:
    """Read the result, and paste it over the selection only after a spoken confirm; else keep it on the clipboard."""
    from ultron.commands.router import active_io
    spoken = result if len(result) <= SPOKEN_CHARS else result[:SPOKEN_CHARS].rsplit(" ", 1)[0] + " and so on"
    if active_io().confirm(f"{spoken}. {ask}"):
        paste_over_selection(result)
        return "Pasted."
    _clip_set(result)
    return "Not pasted. It's on your clipboard if you want it."


@command("rewrite_selection", "Rewrite the highlighted text as asked and paste it after a spoken confirm.", group=_GROUP,
         title="rewrite the selected text {instruction}", priority=62,
         params=[Param("instruction", "str", "how to change it, for example more polite or fix the grammar",
                       cues=("make this", "make that", "rewrite this", "rewrite"))],
         rules=[rf"make {_THIS.replace('|it|', '|')} (?P<instruction>(?:(?:a bit|a little|slightly|much|way|more|less|bit) )?"
                r"(?:polite|politer|formal|informal|casual|friendly|professional|short|shorter|longer|concise|simple|simpler|"
                r"clear|clearer|natural|direct|positive|persuasive|polished|neutral|warm|firm|better|nicer|detailed|brief|"
                r"readable|confident|humble|apologetic|gentle|sound(?:ing)? .+)(?: and \w+)?)",
                rf"(?:rewrite|rephrase|reword|redo|polish up|improve) {_THIS} (?P<instruction>.+)",
                rf"(?P<instruction>rewrite|rephrase|reword|proofread|polish|shorten|simplify|paraphrase|improve) {_THIS}",
                rf"fix the (?P<instruction>grammar|spelling|typos|punctuation)(?: and \w+)? (?:in|of|on) {_THIS}",
                rf"(?:turn|convert) {_THIS} into (?P<instruction>(?:a )?(?:bullet points?|bullets|list|paragraph|formal|polite|casual) ?.*)"],
         examples=["make this more polite", "rewrite this more formally", "make the selected text shorter",
                   "proofread this", "fix the grammar in this", "make this sound friendlier", "rephrase this",
                   "polish this up", "turn this into bullet points", "make this a bit more professional"],
         not_examples=["make this window bigger", "make it louder", "make this louder", "make the font bigger",
                       "make this a folder", "turn this into a folder"])
def rewrite_selection(instruction: str) -> str:
    text, problem = _selected(REWRITE_LIMIT)
    if problem:
        return problem
    result = _ask(f"Rewrite the text below: {instruction}. Keep the meaning and the language. "
                  f"Output only the rewritten text, nothing else.\n\n{text}",
                  max_tokens=min(1024, len(text) // 2 + 150))
    if not result:
        return MODEL_SILENT
    return _offer_to_paste(result, "Say confirm to paste it over your selection.")


@command("reply_to_selection", "Draft a reply to the highlighted message and paste it after a spoken confirm.",
         group=_GROUP, title="reply to the selected message", priority=63,
         params=[Param("instruction", "str", "what the reply should say", required=False,
                       cues=("saying", "say that", "and say", "and tell them", "telling them"))],
         rules=[rf"(?:draft |write |compose |type |give me )?(?:a |an )?(?:quick |short |polite )?(?:reply|response|answer) to {_THIS}"
                r"(?: (?:saying|and say(?: that)?|and tell them(?: that)?|telling them|that says|with) (?P<instruction>.+))?",
                rf"(?:answer|respond to|reply to) {_THIS}(?: (?:saying|and say(?: that)?|and tell them(?: that)?|telling them|with) (?P<instruction>.+))?"],
         examples=["reply to this", "write a response to the selected message",
                   "reply to this saying i will be late", "answer this for me", "respond to this email politely"],
         not_examples=["draft an email to my manager", "reply to my last email", "draft a reply saying i will be late",
                       "draft a quick reply", "draft a polite reminder email"])
def reply_to_selection(instruction: str = "") -> str:
    text, problem = _selected(REWRITE_LIMIT)
    if problem:
        return problem
    want = instruction.strip() or "a polite, helpful reply"
    result = _ask("Write a short reply to the message below. The reply should say: " + want +
                  ". Output only the reply text, no subject line, no explanation.\n\nMessage:\n" + text,
                  max_tokens=300)
    if not result:
        return MODEL_SILENT
    return _offer_to_paste(result, "Say confirm to paste it over the selected message. Otherwise it stays on your clipboard.")
