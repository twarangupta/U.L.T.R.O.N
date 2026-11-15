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

SECOND_MARGIN = 0.03  # the best command must beat the second best by this much, or ask first

# Static embeddings ignore word order and negation: "don't close chrome" looks like "close chrome".
# So a sentence with a negation, or a time word that defers it ("close chrome later"), never runs a
# command directly, and the LLM is offered no tools for it. Timers and reminders take time words.
_NEGATION = re.compile(r"\b(?:don t|dont|do not|does not|never|not|shouldn t|won t|no need to)\b")
_DEFER = re.compile(r"\b(?:later|tomorrow|tonight|this evening|next week|in the morning|after (?:lunch|dinner|this|that|work)"
                    r"|in (?:a|an|\d+|\w+) (?:few )?(?:second|minute|hour|day)s?|at \d+(?: ?[ap] ?m)?|when i)\b")


# A question about a thing is not a request to do it: "what does git push do", "is it safe to empty
# the recycle bin". Rules still answer "what is my ip"; only the matcher is held back.
_ABOUT = re.compile(r"^(?:what (?:does|do|did)|what is (?:a|an|the (?:meaning|history|difference|point))|what s (?:a|an)"
                    r"|explain (?:what|how|why)|why (?:do|does|is|are|did)|how (?:do|does|can|should) (?:i|you|one|we)"
                    r"|is it (?:safe|ok|okay|good|bad|possible)|tell me about|should i|which is better|who (?:is|was|invented))\b")

# Words that carry no meaning of their own, for the unknown-word check.
_FUNCTION_WORDS = set("""a an the my me i you your it this that these those to of in on at for with and or but
is are was were be been am do does did can could would will should shall please just so now then up down
some any all one there here what s t m re ll d ve let us we our its out off from by as into about over
too very really bit little more again also yeah ok okay hey ultron""".split())


def unknown_words(n: str, cmd: Command) -> set[str]:
    """Content words in the sentence that none of the command's examples, title or description use.

    "restart nginx" has "nginx", which no restart_pc example has: static embeddings
    cannot tell that apart from "restart the pc", this check can.
    """
    vocab = _vocab(cmd.name)
    return {w for w in n.split() if w not in vocab and w not in _FUNCTION_WORDS and not w.isdigit()}


_VOCAB: dict[str, set] = {}


def _vocab(name: str) -> set[str]:
    if name not in _VOCAB:
        from commands import apps
        cmd = registry.get(name)
        words = set()
        for text in (*cmd.examples, cmd.description, cmd.title or "", cmd.name.replace("_", " ")):
            words |= set(clean(text).split())
        for p in cmd.params:
            words |= set(" ".join(p.choices).split())
            if p.type == "app":
                words |= set(" ".join(apps.APP_ALIASES).split())
        _VOCAB[name] = words
    return _VOCAB[name]


def guard(n: str) -> str | None:
    """Why a cleaned sentence must not run a command directly, or None."""
    if _NEGATION.search(n):
        return "negation"
    if _DEFER.search(n):
        return "time"
    return None


def _takes_time(cmd: Command) -> bool:
    return any(p.name == "unit" for p in cmd.params)


YES_WORDS = {"yes", "yeah", "yep", "yup", "correct", "right", "do it", "sure", "yes please", "go ahead",
             "affirmative", "that s right", "yes do it", "confirm"}

NO_WORDS = {"no", "nope", "nah", "no thanks", "never mind", "nevermind", "cancel", "stop", "don t", "dont", "wrong", "negative"}

_REQUEST = re.compile(
    r"^(?:(?:can|could|would|will) you(?: please)?|please|kindly|just|so|now|hey|ok|okay|"
    r"i want you to|i need you to|i d like you to|i would like you to|go ahead and|i said|"
    r"help me|be a dear and|quickly|ultron|yes|yeah)\s+")
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

    def ask_yes_no(self, prompt: str) -> bool | str:
        """Speak prompt. True for a yes, False for a no or silence, or the answer's own words when it
        was neither ("maximize everything"): the router then treats those words as a new sentence."""
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
    scores: dict = field(default_factory=dict)  # candidate -> similarity, for the gate on the LLM's tool call
    sentence: str = ""                          # the cleaned sentence


_announce_seconds = [0.0]  # time spent speaking announcements during this route() call


class Reroute(Exception):
    """The answer to "Did you mean ...?" was a new sentence; route() (or the caller) routes it."""

    def __init__(self, text: str):
        super().__init__(text)
        self.text = text


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
        answer = io.ask_yes_no(f"Did you mean: {cmd.describe(args)}?")
        if isinstance(answer, str) and answer.strip():
            raise Reroute(answer)  # not a yes or no: the answer is the next request
        if not answer:
            return persona.pick(persona.CANCELLED_REPLIES)
    announced = False
    if cmd.doing:
        text = cmd.doing.format(**{k: registry.pretty_value(v) for k, v in args.items()},
                                **{p.name: "" for p in cmd.params if p.name not in args})
        began = time.perf_counter()
        spoken = io.announce(text)  # blocks while ULTRON talks: that is speaking time, not routing time
        _announce_seconds[0] += time.perf_counter() - began
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
    return reply  # the result is always said ("Closed Chrome."), also after the announcement


# ---- stage a: rules ----
def _rule_hits(text: str, n: str, cmds: list[Command]):
    """(command, captured params, the words outside the params) for every rule that fits."""
    for cmd in cmds:
        target = text.strip() if cmd.raw else n
        for rule in cmd.rules:
            m = rule.fullmatch(target)
            if m:
                free_text = {p.name for p in cmd.params if p.type == "str"}
                outside, last = [], 0
                for name in m.groupdict():
                    if m.group(name) and name in free_text:  # "chrome later" as an app still counts
                        outside.append(target[last:m.start(name)])
                        last = m.end(name)
                outside.append(target[last:])
                yield cmd, {k: v for k, v in m.groupdict().items() if v}, normalize(" ".join(outside))


def _stage_rules(text: str, n: str, io: Interaction, cmds: list[Command]) -> Outcome | None:
    for cmd, raw_args, outside in _rule_hits(text, n, cmds):
        blocked = guard(outside)  # "remember that I do not drink coffee": the negation is the fact
        if blocked and not (cmd.stages == ("rule",) or (blocked == "time" and _takes_time(cmd))):
            continue  # dictation still types "don't restart"; timers keep their time words
        try:
            args = cmd.validate(raw_args)
        except ArgumentError:
            continue
        if not _apps_resolve(cmd, args):
            continue  # "show me the desktop", "start over": an app rule, but no such app
        reply = execute(cmd, args, io)
        if reply is not None:
            return Outcome(reply, "rule", cmd.name, args, 1.0)
    return None


def _apps_resolve(cmd: Command, args: dict) -> bool:
    """Every app parameter names a real app; extra words are trimmed in place ("clod the application")."""
    from commands import apps
    for p in cmd.params:
        if p.type == "app" and p.name in args:
            name = apps.resolve_name(args[p.name], sound_alike=cmd.name == "open_app" or cmd.group == "Windows and apps")
            if name is None:
                return False
            args[p.name] = apps.canonical(name)
    return True


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
    blocked = guard(n)
    if blocked and not (blocked == "time" and _takes_time(cmd)):
        return None, ranked
    if _ABOUT.search(n):
        return None, ranked  # a question about it: the LLM answers, and may still call a tool
    free_text = any(p.type == "str" for p in cmd.params)
    strange = set() if free_text else unknown_words(n, cmd)
    if strange and cmd.risk == "confirm":
        return None, ranked  # never offer to shut down for "shut down the old project"
    if top.score >= ASK_SCORE and top.margin >= MARGIN:
        try:
            args = cmd.validate(slots.fill(cmd, n))
        except ArgumentError:
            args = None  # a parameter is missing: the LLM can fill it
        if args is not None:
            runner_up = ranked[1].score if len(ranked) > 1 else 0.0
            sure = (top.score >= RUN_SCORE and len(n.split()) >= SHORT_WORDS
                    and top.score - runner_up >= SECOND_MARGIN and not strange)
            reply = execute(cmd, args, io, sure=sure)
            if reply is not None:
                return Outcome(reply, "match", cmd.name, args, top.score), ranked
    return None, ranked


def route(text: str, io: Interaction | None = None, use_matcher: bool = True, _rerouted: bool = False) -> Outcome:
    """Stages a and b. Route "llm" means: ask the LLM, offering outcome.candidates as tools.

    If the answer to a "Did you mean" question was a new sentence, that sentence is routed instead
    (once: it cannot start another chain of questions).
    """
    try:
        return _route(text, io, use_matcher)
    except Reroute as again:
        if _rerouted:
            return Outcome("", "rule")
        from logger import logger
        logger.info(f"Did-you-mean answer {again.text!r} is a new request")
        return route(again.text, io, use_matcher, _rerouted=True)


def _route(text: str, io: Interaction | None, use_matcher: bool) -> Outcome:
    io = io or Interaction()
    timings: dict = {}
    from commands import context
    if context.pending == "rename_name":  # "What should I call it?" was asked: the answer is the name
        context.pending = None
        if normalize(text) not in NO_WORDS:
            text = f"rename it to {text.strip(' .')}"
    n = clean(text)
    _announce_seconds[0] = 0.0
    start = time.perf_counter()
    outcome = _stage_rules(text, n, io, registry.commands("rule"))
    timings["rule_ms"] = (time.perf_counter() - start - _announce_seconds[0]) * 1000
    if _announce_seconds[0]:
        timings["announce_ms"] = _announce_seconds[0] * 1000
    if outcome:
        outcome.timings = timings
        return outcome
    ranked = []
    if use_matcher and n:
        outcome, ranked = _stage_match(n, io, timings)
        if outcome:
            outcome.timings = timings
            return outcome
    blocked = guard(n)
    if blocked:  # no tools: the LLM answers in words ("close chrome later" has no scheduler)
        ranked = [r for r in ranked if blocked == "time" and _takes_time(registry.get(r.command))]
    candidates = tool_candidates(ranked)
    top = ranked[0].score if ranked else None
    scores = {r.command: r.score for r in ranked}
    return Outcome(None, "llm", score=top, timings=timings, candidates=candidates, scores=scores, sentence=n)


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


# ---- the gate on the LLM's tool call ----
# A small model will happily call the nearest tool for anything ("it isn't open" -> continue_work,
# "turn on Bluetooth" -> volume_up). So a tool call runs only if the sentence really resembles that
# command's examples and uses no unexplained content words. Measured in tools/intent_eval.py (D31).
GATE_RUN = 0.50       # similarity to the command's examples: run (unless something looks off, below)
GATE_ASK = 0.47       # between ASK and RUN: "Did you mean ...?"; below: not this command
SMELL_MAX = 0.65      # below this, a sentence that looks off cannot run unasked
GATE_TIE = 0.03       # a runner-up this close means the model had no real reason to pick this one


_REQUESTY = re.compile(r"^(?:(?:can|could|would|will) you|please|i want you to|i need you to|turn|switch|enable|disable|"
                       r"set|start|stop|connect|disconnect|open|launch|make|show|put|change|increase|decrease|toggle|"
                       r"pair|install|run|play)\b")


def gate(sentence: str, cmd: Command, score: float | None, args: dict, scores: dict | None = None) -> str:
    """"run", "ask" or "no" for a tool call the LLM made for this sentence.

    Two smells weaken a middling match: the sentence has content words the command never uses
    ("bluetooth" for volume_up), and another command scores almost the same (mute, unmute and
    volume_up all fit "turn on bluetooth" equally badly). One smell means ask first; both mean no.
    """
    score = score or 0.0
    if score < GATE_ASK or not _apps_resolve(cmd, dict(args)):
        return "no"
    smells = 0
    if cmd.risk != "confirm" and not any(p.type == "str" for p in cmd.params) and unknown_words(sentence, cmd):
        smells += 1
    others = [v for k, v in (scores or {}).items() if k != cmd.name]
    if others and max(others) >= score - GATE_TIE:
        smells += 1
    if smells and score < SMELL_MAX:
        return "no" if smells > 1 else "ask"
    return "run" if score >= GATE_RUN else "ask"


def looks_like_request(text: str) -> bool:
    """An instruction ("turn on Bluetooth"), as opposed to a remark or a question."""
    return bool(_REQUESTY.match(normalize(text)))


def run_tool_call(name: str, arguments: dict | None, offered: list[str], io: Interaction | None = None,
                  scores: dict | None = None, sentence: str | None = None) -> Outcome | None:
    """Run a tool call from the LLM if it is valid and passes the gate; None if it must be ignored.

    With scores and sentence (the router's own numbers) the gate applies; a request that no
    command fits comes back as a route "refused" outcome, an honest "I can't do that yet".
    """
    cmd = registry.get(name)
    if cmd is None or name not in offered or "tool" not in cmd.stages:
        return None
    try:
        args = cmd.validate(arguments)
    except ArgumentError:
        return None
    sure = True
    if scores is not None and sentence is not None:
        verdict = gate(sentence, cmd, scores.get(name), args, scores)
        if verdict == "no":
            if looks_like_request(sentence):
                return Outcome(persona.pick(persona.CANT_DO_REPLIES), "refused", None, {}, scores.get(name))
            return None
        sure = verdict == "run"
    try:
        reply = execute(cmd, args, io or Interaction(), sure=sure)
    except Reroute as again:
        return Outcome(None, "reroute", sentence=again.text)
    if reply is None:
        return None
    return Outcome(reply, "tool", cmd.name, args)


# ---- repairs: "not base, best", "it isn't open", "that's wrong" ----
_SWAP = re.compile(r"^(?:no |nope |i said )?not (?P<old>.+?)(?: but| rather| i said| i meant)? (?P<new>[a-z0-9][a-z0-9 ]*)$")
_COMPLAINT = re.compile(
    r"^(?:(?:it|that|this|they) (?:is not|isn t|was not|wasn t|did not|didn t|does not|doesn t|still (?:is not|isn t|didn t|doesn t)|never)"
    r"|that s (?:not right|wrong|not what i (?:said|asked|meant))|that was (?:wrong|not right)|nothing happened"
    r"|no that s not (?:right|what i (?:said|asked|meant))|wrong one|not that one)\b")


def repair(text: str, io: Interaction | None = None) -> Outcome | None:
    try:
        return _repair(text, io)
    except Reroute as again:
        return Outcome(None, "reroute", sentence=again.text)


def _repair(text: str, io: Interaction | None = None) -> Outcome | None:
    """Treat a correction or complaint as being about the last command, never as a new one.

    "not base, best" re-runs the last command with that word swapped in its text parameter;
    a plain complaint says what was done and offers to retry. None: not a repair.
    """
    from commands import context
    last = context.last_run
    n = normalize(text)
    if last is None or not n:
        return None
    cmd = registry.get(last.command)
    if cmd is None:
        return None
    io = io or Interaction()
    if _COMPLAINT.match(n):
        done = last.reply.rstrip(". ") or cmd.describe(last.args)
        answer = io.ask_yes_no(f"Last I did: {done}. {persona.RETRY_OFFER}")
        if isinstance(answer, str) and answer.strip():
            raise Reroute(answer)  # neither yes nor no: a new request
        if answer:
            reply = execute(cmd, dict(last.args), io)
            return Outcome(reply if reply is not None else "", "repair", cmd.name, last.args)
        return Outcome("", "repair", cmd.name, last.args)
    swap = _SWAP.match(n)
    if swap:
        old, new = swap["old"].strip(), swap["new"].strip()
        for pname, value in last.args.items():
            if isinstance(value, str) and re.search(rf"\b{re.escape(old)}\b", value, re.I):
                args = dict(last.args, **{pname: re.sub(rf"\b{re.escape(old)}\b", new, value, count=1, flags=re.I)})
                reply = execute(cmd, args, io)
                if reply is not None:
                    return Outcome(reply, "repair", cmd.name, args)
    return None
