

from ultron.stt import corrections  # noqa: E402
import stt_benchmark as bench  # noqa: E402


def test_word_errors():
    assert bench.word_errors("git push", "git push") == 0
    assert bench.word_errors("git push", "get push") == 1
    assert bench.word_errors("open vs code", "open code") == 1
    assert bench.word_errors("stop", "assets stop") == 1


def test_mishearings_keep_a_neighbour_word():
    assert bench.mishearings("open chrome", "open pro") == [("open pro", "open chrome")]
    assert bench.mishearings("git pull", "get pull") == [("get pull", "git pull")]


def test_suggestion_matches_raw_text_with_apostrophe():
    rules = corrections.compile_rules({"it s status": "git status"})
    assert corrections.apply("It's status.", rules) == "git status."


def test_recommend_prefers_accuracy_then_speed():
    results = [
        {"model": "base.en", "wer_fixed": 36.0, "median_s": 0.9},
        {"model": "small", "wer_fixed": 8.0, "median_s": 1.6},
        {"model": "base", "wer_fixed": 9.5, "median_s": 1.1},
    ]
    assert bench.recommend(results)["model"] == "base"
