"""Stages a and b on tests/intents.yaml (D30): accuracy floors and the safety property.

Silent and light: handlers run in dry-run mode, no audio, no LLM. Skipped when the
30 MB matcher model is not downloaded. The full report: tools/intent_eval.py.
"""

import pytest


from ultron.commands import intent  # noqa: E402

pytestmark = pytest.mark.skipif(not intent.model_available(), reason="meaning-matcher model not downloaded")


@pytest.fixture(scope="module")
def results():
    import intent_eval
    return intent_eval.eval_new(intent_eval.load_cases())


def _share(rs, verdicts):
    return sum(1 for r in rs if r.verdict in verdicts) / max(1, len(rs))


def test_negatives_never_run_a_command(results):
    ran = [r.case.text for r in results if r.case.expected is None and r.verdict == "wrong" and not r.asked]
    # One known gap, kept visible: no file-search command yet, so "search a file" opens a web search.
    assert set(ran) <= {"Can you search a file for me in my PC?"}, ran


def test_owner_phrasings(results):
    heard = [r for r in results if r.case.kind == "heard"]
    assert _share(heard, ("run", "ask")) >= 0.85


def test_paraphrases_right_or_asked(results):
    para = [r for r in results if r.case.kind == "paraphrase"]
    assert _share(para, ("run", "ask")) >= 0.78
    wrong_run = [r for r in para if r.verdict == "wrong" and not r.asked]
    assert len(wrong_run) / len(para) <= 0.01, [r.case.text for r in wrong_run][:10]


def test_every_command_is_reachable(results):
    by_cmd = {}
    for r in results:
        if r.case.kind == "paraphrase":
            by_cmd.setdefault(r.case.expected, []).append(r)
    weak = {name: round(_share(rs, ("run", "ask")), 2) for name, rs in by_cmd.items()
            if _share(rs, ("run", "ask")) < 0.4}
    assert not weak, weak


def test_stages_are_fast(results):
    import time

    from ultron.commands import registry
    from ultron.commands.router import route
    with registry.dry_run():  # never run real commands from a test
        start = time.perf_counter()
        for r in results[:200]:
            route(r.case.text)
        assert (time.perf_counter() - start) / 200 < 0.05
