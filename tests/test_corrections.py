import os
import sys


from ultron.stt import corrections  # noqa: E402

RULES = corrections.compile_rules({"get push": "git push", "v s code": "vs code", "get": "git"})


def fix(text):
    return corrections.apply(text, RULES)


def test_replaces_whole_phrase_any_case():
    assert fix("Get push.") == "git push."


def test_tolerates_punctuation_between_words():
    assert fix("Open V. S. Code") == "Open vs code"


def test_longest_entry_wins():
    assert fix("get push now") == "git push now"


def test_does_not_touch_parts_of_words():
    assert fix("forget it") == "forget it"


def test_shipped_file_loads():
    table = corrections.load()
    assert table["get push"] == "git push"
    assert all(not key.startswith("_") for key in table)
