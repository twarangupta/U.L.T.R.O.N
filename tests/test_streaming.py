import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain  # noqa: E402
from brain import looks_like_tool_text, parse_tool_text, split_sentences  # noqa: E402


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


def test_tool_calls_written_as_text_are_held_and_parsed():
    assert looks_like_tool_text('{"name": "volume_up", "parameters": {}}')
    assert not looks_like_tool_text("Commands are for the weak.")
    assert parse_tool_text('{"name": "volume_set", "parameters": {"level": 40}}') == ("volume_set", {"level": 40})
    assert parse_tool_text("Whey is fine.") is None


def _fake_chat(chunks):
    def chat(**kwargs):
        chat.kwargs = kwargs
        return iter(chunks)
    return chat


def _stream(monkeypatch, chunks, tools=None):
    monkeypatch.setattr(brain.ollama, "chat", _fake_chat(chunks))
    spoken = []
    reply = brain.StreamingReply(brain.brain, "q", spoken.append, tools=tools, remember=False)
    reply.join()
    return reply, spoken


def test_native_tool_call_is_not_spoken(monkeypatch):
    call = {"function": {"name": "volume_up", "arguments": {}}}
    reply, spoken = _stream(monkeypatch, [{"message": {"content": "", "tool_calls": [call]}}],
                            tools=[{"type": "function"}])
    assert reply.tool_call == ("volume_up", {}) and spoken == []
    assert brain.ollama.chat.kwargs["tools"] == [{"type": "function"}]


def test_text_answer_streams_without_tools_argument(monkeypatch):
    chunks = [{"message": {"content": "Whey is the usual pick. "}}, {"message": {"content": "Plant blends work too."}}]
    reply, spoken = _stream(monkeypatch, chunks)
    assert reply.tool_call is None and " ".join(spoken) == "Whey is the usual pick. Plant blends work too."
    assert "tools" not in brain.ollama.chat.kwargs


def test_first_piece_can_end_at_a_comma():
    done, rest = split_sentences("Whey and casein are common, but it depends on your goals. More", first=True)
    assert done == ["Whey and casein are common,", "but it depends on your goals."]
    assert rest == "More"


def test_short_first_clause_waits_for_the_sentence():
    done, rest = split_sentences("Well, maybe", first=True)
    assert done == [] and rest == "Well, maybe"
