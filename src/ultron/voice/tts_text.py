"""Rewrite text so the voice says it the way a person would.

Piper reads "PID" as "pid" and "port 8080" as "eight thousand and eighty".
prepare_for_speech() fixes that before synthesis. Add your own fixes to
pronunciations.json (word -> how to say it) without touching code.
"""
import json
import os
import re

from ultron import paths
from ultron.logger import logger

# Spelled out letter by letter. Matched as whole words, exact case.
ACRONYMS = [
    "AI", "API", "CLI", "CPU", "CSS", "CSV", "GPU", "HDD", "HTML", "IP", "JS",
    "LLM", "NPM", "OS", "PC", "PDF", "PID", "PR", "RAM", "SQL", "SSD", "STT",
    "TTS", "UI", "URL", "USB", "VS",
]
# These read better as words.
SAY_AS_WORD = {"RAM": "ram"}

PRONUNCIATIONS_FILE = os.getenv("PRONUNCIATIONS_FILE", os.path.join(paths.CONFIG_DIR, "pronunciations.json"))


def _load_user_pronunciations() -> dict[str, str]:
    if not os.path.exists(PRONUNCIATIONS_FILE):
        return {}
    try:
        with open(PRONUNCIATIONS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        logger.warning(f"Could not read {PRONUNCIATIONS_FILE}: {e}")
        return {}


USER_PRONUNCIATIONS = _load_user_pronunciations()


def _split_port(match: re.Match) -> str:
    """'port 8080' -> 'port 80 80'; round numbers like 3000 stay as they are."""
    word, number = match.group(1), match.group(2)
    if len(number) == 4 and not number.endswith("00"):
        number = f"{number[:2]} {number[2:]}"
    return f"{word} {number}"


def prepare_for_speech(text: str) -> str:
    # Markdown and code symbols the model sometimes emits
    text = re.sub(r"[*`#\[\]]", "", text)
    text = re.sub(r"(?<=\w)_(?=\w)", " ", text)
    text = text.replace("%", " percent")

    for word, spoken in USER_PRONUNCIATIONS.items():
        text = re.sub(rf"\b{re.escape(word)}\b", spoken, text, flags=re.IGNORECASE)

    text = re.sub(r"\b(ports?)\s+(\d{4,5})\b", _split_port, text, flags=re.IGNORECASE)

    for acronym in ACRONYMS:
        spoken = SAY_AS_WORD.get(acronym, " ".join(acronym))
        text = re.sub(rf"\b{acronym}\b", spoken, text)

    return re.sub(r"\s{2,}", " ", text).strip()
