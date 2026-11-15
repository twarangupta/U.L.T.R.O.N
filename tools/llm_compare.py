"""Compare Ollama models on the LLM tool stage (D30). Uses the GPU: run it only when nothing else needs it.

    venv\\Scripts\\python.exe tools\\llm_compare.py                       default model list
    venv\\Scripts\\python.exe tools\\llm_compare.py llama3.2:3b qwen3:4b  chosen models

For each model: unload every other model (ollama stop), run the sentences the rules and matcher leave
to the LLM with the shortlist, then (llama3.2:3b only unless --full-all) with every command as a tool.
Records right tool, wrong calls on negatives, median first token, VRAM from `ollama ps`, and whether
the model accepts tools at all. Report: results/llm_compare.md and .json. Restores llama3.2:3b loaded.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import intent_eval as ie  # noqa: E402

DEFAULT_MODELS = ["llama3.2:3b", "qwen2.5:3b", "qwen3:4b", "gemma3:4b"]
RESTORE = "llama3.2:3b"


def ollama_ps() -> list[dict]:
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout.strip().splitlines()[1:]
    rows = []
    for line in out:
        parts = line.split()
        if len(parts) >= 5:
            rows.append({"model": parts[0], "size": " ".join(parts[2:4]), "processor": " ".join(parts[4:6])})
    return rows


def unload_all() -> None:
    for row in ollama_ps():
        subprocess.run(["ollama", "stop", row["model"]], capture_output=True)


def accepts_tools(model: str) -> tuple[bool, str]:
    import ollama
    from ultron.commands.router import tool_schemas
    try:
        ollama.chat(model=model, messages=[{"role": "user", "content": "close chrome"}],
                    tools=tool_schemas(["close_app"]), options={"num_predict": 20},
                    **({"think": False} if model.startswith("qwen3") else {}))
        return True, ""
    except Exception as e:  # ollama.ResponseError: "does not support tools"
        return False, str(e)[:200]


def run_one(base: list, model: str, full: bool) -> dict:
    import copy
    results = copy.deepcopy(base)
    ie.eval_llm(results, model, full)
    summary = ie.summarize(results, llm=True)
    return {"model": model, "full_tools": full, "all": summary["all"], "heard": summary.get("heard"),
            "negative": summary.get("negative"), "vague": summary.get("vague"), "vram": ollama_ps()}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    full_all = "--full-all" in sys.argv
    models = args or DEFAULT_MODELS
    base = ie.eval_new(ie.load_cases() + ie.load_vague())
    rows = []
    for model in models:
        unload_all()
        ok, why = accepts_tools(model)
        if not ok:
            rows.append({"model": model, "tools_supported": False, "error": why})
            print(model, "does not accept tools:", why)
            continue
        for full in ([False, True] if (full_all or model == RESTORE) else [False]):
            row = run_one(base, model, full)
            row["tools_supported"] = True
            rows.append(row)
            print(json.dumps(row), flush=True)
    unload_all()
    import ollama
    ollama.generate(model=RESTORE, prompt="", keep_alive=-1)  # load it again and keep it loaded
    os.makedirs(ie.RESULTS, exist_ok=True)
    with open(os.path.join(ie.RESULTS, "llm_compare.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    lines = ["| model | tools | right (of positives) | wrong on negatives | wrong on vague (of 5) | malformed calls | median first token s | VRAM |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r.get("tools_supported"):
            lines.append(f"| {r['model']} | no | - | - | - | - | - | - |")
            continue
        a = r["all"]
        vram = r["vram"][0]["size"] if r["vram"] else "?"
        lines.append(f"| {r['model']}{' (full list)' if r['full_tools'] else ''} | yes | {a.get('with_llm_correct')} | "
                     f"{a.get('llm_wrong')} | {(r.get('vague') or {}).get('llm_wrong', 0)} | {a.get('llm_malformed')} | "
                     f"{a.get('llm_first_token_median')} | {vram} |")
    with open(os.path.join(ie.RESULTS, "llm_compare.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
