"""Turn a sentence into a command: rules, then meaning, then the LLM's tool call (D30).

    outcome = route("can you make it a bit louder", io)
    outcome.reply      what to say ("" = silent, None = not a command: ask the LLM)
    outcome.route      "rule", "match", "tool" or "llm"
    outcome.candidates commands to offer the LLM as tools when route is "llm"

Safety is applied in one place, execute(), whatever stage picked the command:
confirm commands need the spoken "confirm", blocked commands never run,
"doing" commands are announced first (talking over the announcement cancels),
and a low-confidence match asks "Did you mean ...?" before running.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import persona
from commands import registry
from commands.registry import ArgumentError, Command, Done
from commands.text import normalize

# Thresholds for the meaning matcher (cosine similarity, tuned on tests/intents.yaml; see D30).
RUN_SCORE = 0.80      # run at once
ASK_SCORE = 0.62      # ask "Did you mean ...?"
MARGIN = 0.05         # must beat the closest "not a command" sentence by this much
TOOL_FLOOR = 0.35     # offer a command to the LLM only above this
MAX_TOOLS = 6
SHORT_WORDS = 3       # sentences shorter than this never run on a match without asking

YES_WORDS = {"yes", "yeah", "yep", "yup", "correct", "right", "do it", "sure", "yes please", "go ahead",
             "affirmative", "that s right", "yes do it", "confirm"}

_REQUEST = re.compile(
    r"^(?:(?:can|could|would|will) you(?: please)?|please|kindly|just|so|now|hey|ok|okay|"
    r"i want you to|i need you to|i d like you to|i would like you to|go ahead and|i said|"
    r"help me|be a dear and|quickly|ultron)\s+")
_TRAILING = re.compile(r"\s+(?:for me|please|now|right now|quickly|real quick|thanks|thank you)$")


def clean(text: str) -> str:
    """normalize() plus polite request words: "Can you please take a screenshot for me?" -> "take a screenshot"."""
    n = normalize(text)
    while True:
        stripped = _TRAILING.sub("", _REQUEST.sub("", n))
        if stripped == n or not stripped:
            return n
        n = stripped


class Interaction:
    """How the router talks back during a command. The defaults never approve anything."""

    def confirm(self, prompt: str) -> bool:
        """Speak prompt; True only if the user said "confirm"."""
        return False

    def ask_yes_no(self, prompt: str) -> bool:
        """Speak prompt; True only for a yes."""
        return False

    def announce(self, text: str) -> bool | None:
        """Speak text before acting. True: the user talked over it (cancel); False: spoken;
        None: nothing was spoken (no voice), so the result is still said afterwards."""
        return None


class _ConfirmOnly(Interaction):
    def __init__(self, confirm_fn):
        self._confirm = confirm_fn

    def confirm(self, prompt: str) -> bool:
        return bool(self._confirm and self._confirm(prompt))


@dataclass
class Outcome:
    reply: str | None
    route: str
    command: str | None = None
    args: dict = field(default_factory=dict)
    score: float | None = None
    timings: dict = field(default_factory=dict)
    candidates: list[str] = field(default_factory=list)


# ---- safety and running, shared by every stage ----
def execute(cmd: Command, args: dict, io: Interaction, sure: bool = True) -> str | None:
    """Run a chosen command with its safety rules. None means "not mine" (routing goes on)."""
    if cmd.risk == "blocked":
        return persona.pick(persona.REFUSED_REPLIES)
    if cmd.risk == "confirm":
        # The confirm prompt names the action, so it replaces "Did you mean".
        if not io.confirm(persona.pick(persona.CONFIRM_PROMPTS, action=cmd.confirm_text)):
            return persona.pick(persona.CANCELLED_REPLIES)
    elif not sure:
        if not io.ask_yes_no(f"Did you mean: {cmd.describe(args)}?"):
            return persona.pick(persona.CANCELLED_REPLIES)
    announced = False
    if cmd.doing:
        text = cmd.doing.format(**{k: registry.pretty_value(v) for k, v in args.items()},
                                **{p.name: "" for p in cmd.params if p.name not in args})
        spoken = io.announce(text)
        if spoken:
            return ""  # the user talked over it: cancelled, and their words are the next request
        announced = spoken is False
    try:
        reply = registry.call(cmd, args)
    except Exception as e:
        from logger import logger
        logger.error(f"Command {cmd.name}({args}) failed: {e}")
        return f"That failed: {e}"
    if reply is None:
        return None
    if announced and isinstance(reply, Done) and not registry.is_dry_run():
        return ""
    return reply


# ---- stage a: rules ----
def _rule_hits(text: str, n: str, cmds: list[Command]):
    for cmd in cmds:
        target = text.strip() if cmd.raw else n
        for rule in cmd.rules:
            m = rule.fullmatch(target)
            if m:
                yield cmd, {k: v for k, v in m.groupdict().items() if v}


def _stage_rules(text: str, n: str, io: Interaction, cmds: list[Command]) -> Outcome | None:
    for cmd, raw_args in _rule_hits(text, n, cmds):
        try:
            args = cmd.validate(raw_args)
        except ArgumentError:
            continue
        reply = execute(cmd, args, io)
        if reply is not None:
            return Outcome(reply, "rule", cmd.name, args, 1.0)
    return None


def run_rules(text: str, group: str | None = None, names: tuple[str, ...] | None = None,
              io: Interaction | None = None) -> str | None:
    """Rules only, for a subset of commands (old match_* entry points)."""
    cmds = [c for c in registry.commands("rule")
            if (group is None or c.group == group) and (names is None or c.name in names)]
    outcome = _stage_rules(text, clean(text), io or Interaction(), cmds)
    return outcome.reply if outcome else None


# ---- stage b: meaning ----
def _stage_match(n: str, io: Interaction, timings: dict) -> tuple[Outcome | None, list]:
    from commands import intent, slots
    matcher = intent.get_matcher(load=False)
    if matcher is None:
        return None, []
    start = time.perf_counter()
    ranked = matcher.rank(n)
    timings["match_ms"] = (time.perf_counter() - start) * 1000
    if not ranked:
        return None, []
    top = ranked[0]
    cmd = registry.get(top.command)
    if top.score >= ASK_SCORE and top.margin >= MARGIN:
        try:
            args = cmd.validate(slots.fill(cmd, n))
        except ArgumentError:
            args = None  # a parameter is missing: the LLM can fill it
        if args is not None:
            sure = top.score >= RUN_SCORE and len(n.split()) >= SHORT_WORDS
            reply = execute(cmd, args, io, sure=sure)
            if reply is not None:
                return Outcome(reply, "match", cmd.name, args, top.score), ranked
    return None, ranked


def route(text: str, io: Interaction | None = None, use_matcher: bool = True) -> Outcome:
    """Stages a and b. Route "llm" means: ask the LLM, offering outcome.candidates as tools."""
    io = io or Interaction()
    timings: dict = {}
    n = clean(text)
    start = time.perf_counter()
    outcome = _stage_rules(text, n, io, registry.commands("rule"))
    timings["rule_ms"] = (time.perf_counter() - start) * 1000
    if outcome:
        outcome.timings = timings
        return outcome
    ranked = []
    if use_matcher and n:
        outcome, ranked = _stage_match(n, io, timings)
        if outcome:
            outcome.timings = timings
            return outcome
    candidates = tool_candidates(ranked)
    top = ranked[0].score if ranked else None
    return Outcome(None, "llm", score=top, timings=timings, candidates=candidates)


# ---- stage c: the LLM's tool call ----
def tool_candidates(ranked) -> list[str]:
    """The commands worth offering the LLM: similar enough, and not closer to a declared near miss.

    A confirm command is dropped as soon as a "not a command" sentence fits at
    least as well ("restart the dev server" never offers restart_pc).
    """
    out = []
    for r in ranked:
        cmd = registry.get(r.command)
        if r.score < TOOL_FLOOR or cmd is None or "tool" not in cmd.stages:
            continue
        if r.margin < (0.0 if cmd.risk == "confirm" else -MARGIN):
            continue
        out.append(r.command)
        if len(out) == MAX_TOOLS:
            break
    return out


def tool_schemas(names: list[str]) -> list[dict]:
    return [registry.get(name).tool_schema() for name in names if registry.get(name)]


def run_tool_call(name: str, arguments: dict | None, offered: list[str], io: Interaction | None = None) -> Outcome | None:
    """Run a tool call from the LLM if it is valid; None if it must be ignored."""
    cmd = registry.get(name)
    if cmd is None or name not in offered or "tool" not in cmd.stages:
        return None
    try:
        args = cmd.validate(arguments)
    except ArgumentError:
        return None
    reply = execute(cmd, args, io or Interaction())
    if reply is None:
        return None
    return Outcome(reply, "tool", cmd.name, args)
