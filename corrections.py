"""Fix words Whisper keeps mishearing, before ULTRON acts on them.

The list lives in corrections.json ("what it heard": "what you said") so it can
be edited without touching code. Matching is case-insensitive, on whole words,
longest entry first. tools/stt_benchmark.py prints suggested entries from your
own recordings.
"""
from __future__ import annotations

import json
import os
import re

from logger import logger

CORRECTIONS_FILE = os.getenv(
    "CORRECTIONS_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "corrections.json"),
)


def load(path: str = CORRECTIONS_FILE) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")
        return {}
    return {k.lower(): v for k, v in data.items() if not k.startswith("_") and isinstance(v, str)}


def compile_rules(table: dict[str, str]) -> list[tuple[re.Pattern, str]]:
    rules = []
    for heard in sorted(table, key=len, reverse=True):
        words = [re.escape(w) for w in heard.split()]
        if words:
            # Words may be separated by spaces, commas or dots ("get, push").
            pattern = re.compile(r"\b" + r"[\s,.]+".join(words) + r"\b", re.IGNORECASE)
            rules.append((pattern, table[heard]))
    return rules


_rules = compile_rules(load())


def apply(text: str, rules: list[tuple[re.Pattern, str]] | None = None) -> str:
    """Return text with every known mishearing replaced."""
    for pattern, said in (_rules if rules is None else rules):
        text = pattern.sub(said, text)
    return text
