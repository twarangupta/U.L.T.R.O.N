"""Measure how well ULTRON understands phrasings, per stage, on tests/intents.yaml (D30).

    venv\\Scripts\\python.exe tools\\intent_eval.py                 rules + matcher (silent, light)
    venv\\Scripts\\python.exe tools\\intent_eval.py --old           also the old router from p1-fixes
    venv\\Scripts\\python.exe tools\\intent_eval.py --llm llama3.2:3b [--full-tools]
                                                                   also the LLM tool stage (uses the GPU)

Nothing is executed: new handlers run in dry-run mode; the old router runs in a
throw-away copy of p1-fixes with every side effect stubbed. The report goes to
results/intent_eval.md and results/intent_eval.json (not in git).

Scoring. Each sentence has an expected command, or none (a negative):
  run    the right command ran at once           ask    the right command, after "Did you mean"
  wrong  another command ran or was asked        llm    left for the LLM stage
  For negatives, pass means no command at all (dictation typing the words also passes).
The owner's real phrasings (heard) weigh 3, negatives 2, generated paraphrases 1,
because paraphrases written by a model share that model's bias.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CASES_FILE = os.path.join(ROOT, "tests", "intents.yaml")
RESULTS = os.path.join(ROOT, "results")
WEIGHTS = {"heard": 3, "negative": 2, "paraphrase": 1, "vague": 2}


@dataclass
class Case:
    text: str
    expected: str | None
    kind: str  # heard, negative, paraphrase


@dataclass
class Result:
    case: Case
    chosen: str | None = None
    asked: bool = False
    route: str = ""
    candidates: list = field(default_factory=list)
    llm_choice: str | None = None
    llm_first_token: float | None = None
    llm_args: dict | None = None
    llm_malformed: bool = False
    scores: dict = field(default_factory=dict)
    sentence: str = ""

    @property
    def verdict(self) -> str:
        if self.case.expected is None:
            return "pass" if self.chosen in (None, "type_text") else "wrong"
        if self.chosen == self.case.expected:
            return "ask" if self.asked else "run"
        if self.chosen is None:
            return "llm"
        return "wrong"


def load_cases(path: str = CASES_FILE) -> list[Case]:
    import yaml
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cases = [Case(text, None, "negative") for text in data.get("negatives", [])]
    for item in data.get("heard", []):
        cases.append(Case(item["text"], item.get("command"), "heard" if item.get("command") else "negative"))
    for name, phrases in (data.get("paraphrases") or {}).items():
        cases += [Case(text, name, "paraphrase") for text in phrases]
    return cases


def load_vague(path: str = CASES_FILE) -> list[Case]:
    """Vague or off-registry sentences that must not run any command (kind "vague"); LLM comparison only."""
    import yaml
    with open(path, encoding="utf-8") as f:
        return [Case(t, None, "vague") for t in (yaml.safe_load(f).get("llm_must_not_act") or [])]


# ---- the new router ----
def _recording_io():
    from commands.router import Interaction

    class Recorder(Interaction):
        asked = False

        def confirm(self, prompt):
            return True

        def ask_yes_no(self, prompt):
            self.asked = True
            return True

        def announce(self, text):
            return None
    return Recorder()


def eval_new(cases: list[Case]) -> list[Result]:
    import commands  # noqa: F401
    from commands import intent, registry
    from commands.router import route
    intent.get_matcher()
    results = []
    with registry.dry_run():
        for case in cases:
            io = _recording_io()
            out = route(case.text, io)
            results.append(Result(case, out.command, io.asked, out.route, out.candidates,
                                  scores=out.scores, sentence=out.sentence))
    return results


# ---- the old router (p1-fixes), stubbed ----
_OLD_REPLY_TO_COMMAND = [  # first matching start of the old reply -> new command name
    ("Searching Google", "web_search"), ("Opening Gmail", "open_website"), ("Opening Youtube", "open_website"),
    ("Opening Github", "open_website"), ("Opening Reddit", "open_website"), ("Opening Stackoverflow", "open_website"),
    ("Opening Google.", "open_website"), ("Opening your", "open_folder"), ("Opening", "open_app"),
    ("Locking", "lock_pc"), ("CPU load", "system_status"), ("Screenshot", "take_screenshot"),
    ("Media playback", "media_play_pause"), ("Playing next", "media_next"), ("Playing previous", "media_previous"),
    ("Playback stopped", "media_stop"), ("Audio unmuted", "unmute"), ("Audio muted", "mute"),
    ("Volume set", "volume_set"), ("Volume increased", "volume_up"), ("Volume decreased", "volume_down"),
    ("Closing active window", "close_app"), ("Minimizing active", "minimize_windows"),
    ("Meeting mode", "meeting_mode"), ("The battery", "battery_status"), ("No battery", "battery_status"),
    ("C: drive", "disk_space"), ("I've successfully organized", "organize_downloads"),
    ("Your git branch", "git_status"), ("You have", "git_status"), ("Staged all", "git_commit"),
    ("Successfully pushed", "git_push"), ("Successfully pulled", "git_pull"), ("Successfully popped", "git_stash_pop"),
    ("Successfully stashed", "git_stash"), ("No active merge", "git_conflicts"), ("I detected merge", "git_conflicts"),
    ("Here are the last 5", "git_log"), ("Successfully created", "git_create_branch"),
    ("Successfully switched", "git_switch_branch"), ("You are currently", "git_branches"),
    ("I've analyzed", "debug_clipboard_error"), ("Your clipboard is empty", "debug_clipboard_error"),
    ("All your project", "audit_dependencies"), ("API ", "api_request"), ("According to my analysis", "explain_file"),
    ("I've fetched", "container_logs"), ("Which docker", "container_logs"), ("Process with", "check_port"),
    ("No process", "check_port"), ("Successfully terminated", "kill_port"), ("The running docker", "docker_status"),
    ("No active docker", "docker_status"), ("Failed to query Docker", "docker_status"), ("JSON formatted", "format_json"),
    ("Failed to parse clipboard", "format_json"), ("Found matches", "search_codebase"), ("No matches", "search_codebase"),
    ("Pasted the", "boilerplate"), ("I've reviewed", "review_code"), ("No changes detected", "review_code"),
    ("Unit test", "write_unit_test"), ("Project workspace", "start_project"), ("I have scanned", "read_screen"),
    ("The pytesseract", "read_screen"), ("I've drafted", "draft_message"), ("Logged", "log_expense"),
    ("I couldn't identify the expense", "log_expense"), ("You have spent", "spending_summary"),
    ("No expenses", "spending_summary"), ("Calendar file", "show_calendar"), ("Here are your next events", "show_calendar"),
    ("Speed test", "speed_test"), ("Internet connect", "speed_test"), ("Connection is active", "speed_test"),
    ("The translation", "translate"), ("Please tell me what text", "translate"), ("I've saved that", "write_note"),
    ("What note", "write_note"), ("Your notepad", "read_notes"), ("You don't have any notes", "read_notes"),
    ("Starting a timer", "set_timer"), ("is spelled", "spell_word"), ("It is Heads", "flip_coin"),
    ("It is Tails", "flip_coin"), ("It is a ", "roll_die"), ("The answer is", "calculate"), ("Your local IP", "ip_address"),
    ("Here are the top world", "news_headlines"), ("I am currently unable to fetch the news", "news_headlines"),
    ("According to Wikipedia", "wikipedia"), ("I couldn't fetch details from Wikipedia", "wikipedia"),
    ("I will remind you", "set_reminder"), ("In ", "weather"), ("I am currently unable to fetch the weather", "weather"),
    ("It's ", "tell_time"), ("Today is", "tell_date"), ("Closed", "close_app"), ("isn't open", "close_app"),
    ("Everything minimised", "minimize_windows"), ("minimised", "minimize_windows"), ("Windows restored", "restore_windows"),
    ("maximised", "maximize_window"), ("Switched to", "switch_to_app"), ("Reopening", "continue_work"),
]

_OLD_WORKER = r'''
import json, os, sys, types, subprocess, threading, urllib.request, webbrowser
root = sys.argv[1]
sys.path.insert(0, root); os.chdir(root)
os.environ["MEMORY_FILE"] = os.path.join(root, "memory.json")
for name in ["pyautogui", "pyperclip", "pycaw", "pycaw.pycaw", "comtypes", "pytesseract", "speedtest"]:
    m = types.ModuleType(name); sys.modules[name] = m
sys.modules["pyautogui"].__getattr__ = lambda n: (lambda *a, **k: None)
sys.modules["pyperclip"].paste = lambda: ""; sys.modules["pyperclip"].copy = lambda t: None
fake_brain = types.ModuleType("brain"); fake_brain.ask_ai = lambda p: "stub"; fake_brain.ask_once = lambda p: "stub"
sys.modules["brain"] = fake_brain
class P:
    returncode = 0; stdout = "main\n"; stderr = ""
subprocess.run = lambda *a, **k: P(); subprocess.Popen = lambda *a, **k: P()
os.system = lambda *a: 0; os.startfile = lambda *a: None; os.rename = lambda *a: None
webbrowser.open = lambda *a, **k: True
def no_net(*a, **k): raise OSError("offline in eval")
urllib.request.urlopen = no_net
threading.Thread.start = lambda self: None
import commands, commands.windows as w
class W:
    def __init__(self): self.wins = [w.Window(1, "YouTube - Google Chrome", "chrome", 10), w.Window(2, "x - Visual Studio Code", "code", 20)]
    def windows(self): return list(self.wins)
    def foreground(self): return self.wins[0]
    def is_own(self, x): return False
    def __getattr__(self, n): return lambda *a, **k: None
w._Win32 = W
import commands.system as s
s.AudioUtilities = None
out = []
for text in json.load(sys.stdin):
    try:
        reply = commands.execute_command(text, lambda p: False)
    except Exception as e:
        reply = "ERROR " + str(e)
    out.append(reply)
print(json.dumps(out))
'''


# Old replies that name a command only by topic: errors from the stubs, persona lines. Each maps
# to a set; the case counts as right if its expected command is in the set (generous to the old router).
_OLD_TOPICS = [
    ("Failed to take screenshot", {"take_screenshot"}), ("I couldn't locate your", {"open_folder"}),
    ("Failed to adjust volume", {"volume_up", "volume_down", "volume_set", "mute", "unmute"}),
    ("Failed to open", {"open_app", "open_website"}), ("Failed to", None), (" is spelled", {"spell_word"}),
    ("programmers", {"tell_joke"}), ("binary", {"tell_joke"}), ("SQL query", {"tell_joke"}),
]


def _old_command(reply: str | None, expected: str | None = None) -> str | None:
    if reply is None:
        return None
    if reply == "":
        return "type_text"
    if "Not confirmed" in reply or "Cancelled" in reply or "did nothing" in reply.lower():
        return "risky"
    for start, name in _OLD_REPLY_TO_COMMAND:
        if reply.startswith(start) or (start in ("isn't open", "minimised", "maximised") and start in reply):
            return name
    for part, names in _OLD_TOPICS:
        if part in reply:
            if names is None:
                return expected if expected and reply.lower().startswith(f"failed to {expected.split('_')[0]}") else "other"
            return expected if expected in names else sorted(names)[0]
    import persona  # memory and activity commands answer with persona lines
    groups = {"memory": ("remember_fact", "list_memories", "forget_last_fact", "forget_fact", "forget_conversation"),
              "activity": ("day_summary", "continue_work", "morning_brief", "pause_tracking", "resume_tracking",
                           "forget_today", "tracking_status")}
    for lst, group in ((persona.MEMORY_SAVED, "memory"), (persona.MEMORY_EMPTY, "memory"), (persona.MEMORY_FORGOT, "memory"),
                       (persona.MEMORY_NOT_FOUND, "memory"), (persona.CONVERSATION_FORGOTTEN, "memory"),
                       (persona.ACTIVITY_NOTHING, "activity"), (persona.TRACKING_PAUSED, "activity"),
                       (persona.TRACKING_RESUMED, "activity")):
        if reply in lst or reply.startswith("I remember:") or reply.startswith("Yesterday"):
            names = groups[group]
            return expected if expected in names else names[0]
    return "other:" + reply[:40]


def eval_old(cases: list[Case], ref: str = "p1-fixes") -> list[Result]:
    tmp = tempfile.mkdtemp(prefix="ultron_old_")
    archive = subprocess.run(["git", "-C", ROOT, "archive", ref], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", tmp], input=archive, check=True)
    worker = os.path.join(tmp, "_old_worker.py")
    with open(worker, "w", encoding="utf-8") as f:
        f.write(_OLD_WORKER)
    res = subprocess.run([sys.executable, worker, tmp], input=json.dumps([c.text for c in cases]),
                         capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(res.stderr[-2000:])
    replies = json.loads(res.stdout.strip().splitlines()[-1])
    risky = {"shutdown_pc", "restart_pc", "empty_recycle_bin"}
    results = []
    for case, reply in zip(cases, replies):
        chosen = _old_command(reply, case.expected)
        if chosen == "risky":
            chosen = case.expected if case.expected in risky else "restart_pc"
        if chosen == "type_text" and case.expected != "type_text" and case.expected is not None:
            chosen = "other:silent"
        results.append(Result(case, chosen, False, "old"))
    return results


# ---- the LLM tool stage ----
def _malformed(name: str, args: dict | None) -> bool:
    """True when the registry would reject the call, or an argument is a schema or other non-scalar."""
    from commands import registry
    if any(isinstance(v, (dict, list)) for v in (args or {}).values()):
        return True
    try:
        registry.get(name).validate(args)
    except registry.ArgumentError:
        return True
    return False


def eval_llm(results: list[Result], model: str, full_tools: bool = False) -> None:
    """For sentences left to the LLM, ask it with the shortlist (or every command) as tools."""
    import ollama

    from commands import registry
    from commands.router import tool_schemas
    from config import OLLAMA_SYSTEM_PROMPT
    all_names = [c.name for c in registry.commands("tool")]
    for r in results:
        if r.route != "llm":
            continue
        names = all_names if full_tools else r.candidates
        kwargs = {"tools": tool_schemas(names)} if names else {}
        if model.startswith("qwen3"):
            kwargs["think"] = False
        start = time.perf_counter()
        first = None
        choice = None
        for part in ollama.chat(model=model, stream=True, keep_alive=-1, options={"num_predict": 60},
                                messages=[{"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
                                          {"role": "user", "content": r.case.text}], **kwargs):
            if first is None:
                first = time.perf_counter() - start
            calls = part.message.tool_calls or []
            if calls:
                choice = calls[0].function.name
                r.llm_args = dict(calls[0].function.arguments or {})
                break
        r.llm_first_token = first
        r.llm_choice = choice if (choice in names) else None
        r.llm_malformed = bool(r.llm_choice) and _malformed(r.llm_choice, r.llm_args)


# ---- report ----
def summarize(results: list[Result], llm: bool = False) -> dict:
    rows = {}
    for kind in ("heard", "paraphrase", "negative", "vague", "all"):
        rs = [r for r in results if kind == "all" or r.case.kind == kind]
        if not rs:
            continue
        counts = {}
        for r in rs:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
        pos = [r for r in rs if r.case.expected]
        row = {"n": len(rs), **counts}
        if pos:
            row["shortlist_has_it"] = sum(1 for r in pos if r.verdict == "llm" and r.case.expected in r.candidates)
        if llm:
            after = sum(1 for r in pos if r.verdict in ("run", "ask")
                        or (r.verdict == "llm" and r.llm_choice == r.case.expected))
            row["with_llm_correct"] = after
            row["llm_wrong"] = sum(1 for r in rs if r.verdict in ("llm", "pass") and r.llm_choice
                                   and r.llm_choice != r.case.expected)
            row["llm_malformed"] = sum(1 for r in rs if r.llm_malformed)
            times = sorted(r.llm_first_token for r in rs if r.llm_first_token)
            if times:
                row["llm_first_token_median"] = round(times[len(times) // 2], 2)
        rows[kind] = row
    weighted_ok = sum(WEIGHTS[r.case.kind] for r in results if r.verdict in ("run", "ask", "pass"))
    weighted_all = sum(WEIGHTS[r.case.kind] for r in results)
    rows["weighted_correct_percent"] = round(100 * weighted_ok / weighted_all, 1)
    rows["wrong_examples"] = [f"{r.case.text!r}: expected {r.case.expected}, got {r.chosen}"
                              for r in results if r.verdict == "wrong"][:40]
    return rows


def gate_report(results: list[Result]) -> dict:
    """What the gate on the LLM's tool call (router.gate) costs and saves, for sentences that reach the LLM.

    positives: cases left for the LLM whose right command is on the shortlist; "kept" = the gate lets
    that call run or asks. negatives: sentences that must not run anything; "open" = some shortlisted
    command would still pass the gate (the LLM could act), before the gate: any shortlisted command.
    """
    from commands import registry
    from commands.router import gate
    pos = [r for r in results if r.verdict == "llm" and r.case.expected in r.candidates]
    kept = {"run": 0, "ask": 0, "no": 0}
    for r in pos:
        kept[gate(r.sentence, registry.get(r.case.expected), r.scores.get(r.case.expected), {}, r.scores)] += 1
    negs = [r for r in results if r.case.expected is None and r.verdict == "pass" and r.candidates]
    open_after = sum(1 for r in negs if any(
        gate(r.sentence, registry.get(c), r.scores.get(c), {}, r.scores) != "no" for c in r.candidates))
    acts = sum(1 for r in negs if any(
        gate(r.sentence, registry.get(c), r.scores.get(c), {}, r.scores) == "run" for c in r.candidates))
    return {"positives_for_llm": len(pos), "gate_run": kept["run"], "gate_ask": kept["ask"], "gate_no": kept["no"],
            "negatives_with_candidates": len(negs), "negatives_still_open_after_gate": open_after,
            "negatives_that_could_run_unasked": acts}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", action="store_true", help="also evaluate the old router (p1-fixes)")
    ap.add_argument("--llm", help="Ollama model for the tool stage, e.g. llama3.2:3b")
    ap.add_argument("--full-tools", action="store_true", help="offer every command as a tool, not the shortlist")
    args = ap.parse_args()
    cases = load_cases()
    report = {}
    start = time.perf_counter()
    new = eval_new(cases)
    report["new"] = summarize(new)
    report["new"]["seconds"] = round(time.perf_counter() - start, 2)
    report["gate"] = gate_report(new)
    if args.old:
        report["old"] = summarize(eval_old(cases))
    if args.llm:
        eval_llm(new, args.llm, args.full_tools)
        report[f"llm {args.llm}{' full' if args.full_tools else ''}"] = summarize(new, llm=True)
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "intent_eval.json"), "w", encoding="utf-8") as f:
        json.dump({"report": report, "results": [dict(asdict(r), verdict=r.verdict) for r in new]}, f, indent=1)
    lines = ["# Intent eval", ""]
    for name, rows in report.items():
        lines.append(f"## {name}")
        for key, value in rows.items():
            if key == "wrong_examples":
                lines += ["", "Wrong:"] + [f"- {w}" for w in value]
            else:
                lines.append(f"- {key}: {value}")
        lines.append("")
    with open(os.path.join(RESULTS, "intent_eval.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
