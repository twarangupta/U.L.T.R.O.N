"""Measure how well ULTRON understands phrasings, per stage, on tests/intents.yaml (D30).

    venv\\Scripts\\python.exe tools\\intent_eval.py                 rules + matcher (silent, light)
    venv\\Scripts\\python.exe tools\\intent_eval.py --llm llama3.2:3b [--full-tools]
                                                                   also the LLM tool stage (uses the GPU)

Nothing is executed: handlers run in dry-run mode. The report goes to
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
import sys
import time
from dataclasses import asdict, dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
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
    from ultron.commands.router import Interaction

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
    from ultron import commands  # noqa: F401
    from ultron.commands import intent, registry
    from ultron.commands.router import route
    intent.get_matcher()
    results = []
    with registry.dry_run():
        for case in cases:
            io = _recording_io()
            out = route(case.text, io)
            results.append(Result(case, out.command, io.asked, out.route, out.candidates,
                                  scores=out.scores, sentence=out.sentence))
    return results


# ---- the LLM tool stage ----
def _malformed(name: str, args: dict | None) -> bool:
    """True when the registry would reject the call, or an argument is a schema or other non-scalar."""
    from ultron.commands import registry
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

    from ultron.commands import registry
    from ultron.commands.router import tool_schemas
    from ultron.config import OLLAMA_SYSTEM_PROMPT
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
    from ultron.commands import registry
    from ultron.commands.router import gate
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
