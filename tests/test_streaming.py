import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import looks_like_command, split_sentences  # noqa: E402


def test_split_keeps_unfinished_rest():
    done, rest = split_sentences("Protein powder is fine. Whey is the usual pick. Plant blends")
    assert done == ["Protein powder is fine.", "Whey is the usual pick."]
    assert rest == "Plant blends"


def test_short_fragments_and_decimals_do_not_split():
    done, rest = split_sentences("Use 3.5 grams. Ok. That is all you need to know. ")
    assert done == ["Use 3.5 grams.", "Ok. That is all you need to know."]


def test_question_and_exclamation_end_sentences():
    done, _ = split_sentences("Really, again with this? Fine, I will explain! ")
    assert done == ["Really, again with this?", "Fine, I will explain!"]


def test_command_replies_are_detected():
    assert looks_like_command("[COMMAND: git status] Checking.")
    assert looks_like_command("`[COMMAND: mute]`")
    assert looks_like_command("COMMAND: volume up")
    assert not looks_like_command("Commands are for the weak.")


def test_first_piece_can_end_at_a_comma():
    done, rest = split_sentences("Whey and casein are common, but it depends on your goals. More", first=True)
    assert done == ["Whey and casein are common,", "but it depends on your goals."]
    assert rest == "More"


def test_short_first_clause_waits_for_the_sentence():
    done, rest = split_sentences("Well, maybe", first=True)
    assert done == [] and rest == "Well, maybe"
