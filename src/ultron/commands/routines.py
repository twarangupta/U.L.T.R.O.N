"""Routines: a named list of things you would say, run in order (D37).

    "run work mode"                   "start my morning routine"
    "remember this as work mode"      records the last 3 things you asked for
    "remember the last 5 commands as work mode"
    "list my routines"                "delete the work mode routine" (asks to confirm)

Routines live in data/routines.yaml (config/routines.example.yaml shows the format and is
yours to copy). A step is any sentence ULTRON understands. Every step goes through the router
like a spoken sentence, so confirms stay in force ("shut down" still asks), and the first step
that fails or is refused stops the routine with an honest message.
"""
from __future__ import annotations

import os
import time

from ultron import paths
from ultron.commands import context, registry
from ultron.commands.registry import Param, command
from ultron.commands.text import normalize

_GROUP = "Routines"
DEFAULT_RECORD = 3
MAX_STEPS = 12
STEP_PAUSE = 0.4  # seconds between steps, so one app has started opening before the next command

_FILLER = {"my", "the", "a", "routine", "macro", "mode", "routines"}
# "start focus mode" and "switch to dark mode" are ordinary commands, never routines
_BUILT_IN_MODES = (r"(?:focus|meeting|dark|light|normal|do not disturb|airplane|flight|night|game|gaming|presentation|"
                   r"sleep|silent|quiet|battery saver|power saver|tablet|safe)")
_running: list[bool] = []
NESTED = "A routine cannot start another routine. I would never finish."


class RoutineFileError(Exception):
    """data/routines.yaml cannot be read."""


# ---- the file ----
def _key(name: str) -> str:
    """Compare names loosely: "my work routine", "work mode" and "Work" are the same routine."""
    return " ".join(w for w in normalize(name).split() if w not in _FILLER)


def load() -> dict[str, list[str]]:
    """name -> steps. Missing file: no routines. A broken file raises RoutineFileError."""
    import yaml
    if not os.path.exists(paths.ROUTINES_FILE):
        return {}
    try:
        with open(paths.ROUTINES_FILE, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        raise RoutineFileError(str(e)) from e
    if not isinstance(raw, dict):
        raise RoutineFileError("the top level must be a list of routine names")
    out = {}
    for name, steps in raw.items():
        if isinstance(steps, dict):  # allow {steps: [...]} so notes can sit next to them
            steps = steps.get("steps")
        if isinstance(steps, list) and all(isinstance(s, str) and s.strip() for s in steps) and steps:
            out[str(name).strip()] = [s.strip() for s in steps]
    return out


def save(routines: dict[str, list[str]]):
    import yaml
    os.makedirs(os.path.dirname(paths.ROUTINES_FILE), exist_ok=True)
    with open(paths.ROUTINES_FILE, "w", encoding="utf-8") as f:
        f.write("# Your routines. Each step is a sentence ULTRON understands. Edit freely.\n")
        yaml.safe_dump(routines, f, sort_keys=False, allow_unicode=True, default_flow_style=False)


def find(name: str, routines: dict[str, list[str]]) -> str | None:
    """The stored name that the spoken name means, allowing small mishearings."""
    wanted = _key(name)
    if not wanted:
        return None
    by_key = {_key(n): n for n in routines}
    if wanted in by_key:
        return by_key[wanted]
    from ultron.commands.apps import fuzzy
    best = fuzzy(wanted, list(by_key))
    return by_key[best] if best else None


def _say_list(items: list[str]) -> str:
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else items[0]


# ---- running ----
def run_steps(name: str, steps: list[str]) -> str:
    """Run the steps through the router, in order. Stops at the first one that fails or is refused."""
    from ultron import persona
    from ultron.commands.router import active_io, route
    io = active_io()
    stopped = set(persona.CANCELLED_REPLIES) | set(persona.REFUSED_REPLIES) | set(persona.CANT_DO_REPLIES)
    _running.append(True)
    try:
        for number, step in enumerate(steps, 1):
            outcome = route(step, io, _rerouted=True)
            reply = outcome.reply
            if outcome.command is None and reply == "":  # a "did you mean" answer turned into a new request
                return f"I stopped {name} at step {number}, {step}, because you changed the subject."
            if outcome.command is None or reply is None:
                return (f"I stopped {name} at step {number}, {step}. "
                        "That is not something I know how to do, so I did nothing more.")
            if reply in stopped or reply == NESTED or reply.startswith("That failed") or outcome.route == "refused":
                return f"I stopped {name} at step {number}, {step}. " + (reply if reply not in stopped else "It was cancelled.")
            if number < len(steps) and not registry._dry_run[0]:
                time.sleep(STEP_PAUSE)
    finally:
        _running.pop()
    return f"{name.capitalize()} is done. {len(steps)} step{'s' if len(steps) != 1 else ''}."


@command("run_routine", "Run a saved routine: a named list of commands (work mode, morning routine).", group=_GROUP,
         title="run the {name} routine", priority=70,
         params=[Param("name", "str", "the routine's name, for example work mode", cues=("run", "start", "launch", "activate"))],
         rules=[r"(?:run|start|launch|activate|begin|trigger|do|kick off|fire up) (?:my |the )?(?P<name>[a-z0-9 ]+?) (?:routine|macro)",
                rf"(?:run|start|launch|activate|begin|trigger|kick off|switch to|go into|enter) (?:my |the )?(?!{_BUILT_IN_MODES} mode)(?P<name>[a-z0-9 ]+ mode)",
                r"(?:run|start|launch|activate) (?:my |the )?(?:routine|macro) (?:called |named )?(?P<name>[a-z0-9 ]+)"],
         examples=["run study mode", "start my morning routine", "run the gym routine", "activate coding mode",
                   "launch my evening routine", "kick off my reading routine", "trigger the cleanup macro"],
         not_examples=["run a speed test", "start the dev server", "run the tests", "start timer", "run git status"])
def run_routine(name: str) -> str | None:
    if _running:
        return NESTED
    try:
        routines = load()
    except RoutineFileError as e:
        return f"I can't read your routines file: {e}"
    found = find(name, routines)
    if found is None:
        if name.strip().endswith(" mode"):
            return None  # "start focus mode" may be an ordinary command, routing goes on
        known = list(routines)
        return (f"I don't have a routine called {name}. You have: {_say_list(known)}." if known
                else f"I don't have a routine called {name}. You have none yet. Run a few commands, then say remember this as {name}.")
    steps = routines[found]
    return run_steps(found, steps)


@command("remember_routine", "Save the last few commands the user gave as a named routine.", group=_GROUP,
         title="remember the last {count} commands as {name}", priority=80,
         params=[Param("name", "str", "the routine's name", cues=("as",)),
                 Param("count", "int", "how many recent commands to save", required=False)],
         rules=[r"(?:remember|save|record|store|keep) (?:this|that|these|those|all this|the last (?P<count>\w+) (?:commands?|things|steps|actions)|"
                r"what i just did) (?:as|under|and call it|called|and name it|with the name) (?:the )?(?P<name>[a-z0-9 ]+?)(?: routine| macro)?",
                r"(?:make|create) (?:a |my )?(?:routine|macro) (?:called |named |for )?(?P<name>[a-z0-9 ]+?) from (?:this|that|the last (?P<count>\w+) (?:commands?|things))"],
         examples=["remember this as study mode", "save that as my morning routine", "remember the last 4 commands as study mode",
                   "record what i just did as the gym routine", "save this as a macro called setup",
                   "remember those as coding mode"],
         not_examples=["remember that my standup is at 10", "remember my sister's name is asha",
                       "remember this meeting is at ten"])
def remember_routine(name: str, count: int = DEFAULT_RECORD) -> str:
    count = max(1, min(int(count), MAX_STEPS))
    recent = list(context.history)[-count:]
    if not recent:
        return "I haven't run any commands to save yet. Do the things first, then say remember this as a name."
    try:
        routines = load()
    except RoutineFileError as e:
        return f"I can't read your routines file, so I saved nothing: {e}"
    words = normalize(name).split()
    while words and words[0] in ("my", "the", "a"):
        words.pop(0)
    while words and words[-1] in ("routine", "macro"):
        words.pop()
    name = " ".join(words)
    if not name:
        return "What should I call it? Say remember this as, then a name."
    existing = find(name, routines)
    replaced = existing is not None
    if replaced:
        name = existing  # keep the name it was saved under
        routines.pop(existing)
    routines[name] = recent
    save(routines)
    note = " It replaces the old one." if replaced else ""
    return f"Saved {name} with {len(recent)} step{'s' if len(recent) != 1 else ''}: {_say_list(recent)}.{note}"


@command("list_routines", "Say the names of the saved routines.", group=_GROUP, title="list my routines", priority=70,
         rules=[r"(?:list|show|say|read|what are|tell me)(?: me)?(?: all| out)?(?: of)?(?: my| the)? (?:routines|macros)",
                r"what (?:routines|macros) do i have|which routines (?:do i have|are there|exist)|do i have (?:any )?(?:routines|macros)"],
         examples=["list my routines", "what routines do i have", "show my macros", "which routines are saved",
                   "tell me my routines", "do i have any routines"],
         not_examples=["list my files", "what are my notes", "list my memories"])
def list_routines() -> str:
    try:
        routines = load()
    except RoutineFileError as e:
        return f"I can't read your routines file: {e}"
    if not routines:
        return "You have no routines yet. Run a few commands, then say remember this as a name."
    parts = [f"{n}, {len(s)} step{'s' if len(s) != 1 else ''}" for n, s in routines.items()]
    return "Your routines: " + "; ".join(parts) + "."


@command("delete_routine", "Delete a saved routine.", group=_GROUP, title="delete the {name} routine", priority=70,
         risk="confirm", confirm_text="delete the {name} routine",
         params=[Param("name", "str", "the routine's name", cues=("delete", "remove", "forget"))],
         rules=[r"(?:delete|remove|erase|forget|get rid of|scrap) (?:my |the )?(?P<name>[a-z0-9 ]+?) (?:routine|macro)",
                r"(?:delete|remove|erase|forget|scrap) (?:my |the )?(?:routine|macro) (?:called |named )?(?P<name>[a-z0-9 ]+)"],
         examples=["delete the study mode routine", "remove my morning routine", "forget the gym routine",
                   "get rid of the study macro", "erase my evening routine"],
         not_examples=["delete the file", "forget that my sister is asha", "delete my last email"])
def delete_routine(name: str) -> str:
    try:
        routines = load()
    except RoutineFileError as e:
        return f"I can't read your routines file: {e}"
    found = find(name, routines)
    if found is None:
        return f"I don't have a routine called {name}, so nothing was deleted."
    routines.pop(found)
    save(routines)
    return f"Deleted {found}."
