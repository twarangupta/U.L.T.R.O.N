"""The LLM may only trigger a command when the user's words are about it."""
import pytest

from commands.ai_routing import allowed_ai_command

BLOCKED = [
    ("Assets stop.", "git log"),                       # misheard "stop"
    ("I meant on the wave protein.", "git log"),       # misheard "whey", follow-up question
    ("what is the best protein powder", "git status"),
    ("tell me the history of India", "git log"),
    ("hold on what is the weather", "git stash"),
    ("tell me a joke about cats", "git push"),
    ("what is the weather today", "shutdown"),         # not an AI command at all
    ("play some music for me", "volume up"),
    ("can you open the door", "lock pc"),
]

ALLOWED = [
    ("show me my git history", "git log"),
    ("what were my last commits", "git log"),
    ("what's the git status", "git status"),
    ("stash my changes please", "git stash"),
    ("sync my repo with remote", "git pull"),
    ("push my changes to github", "git push"),
    ("turn the volume up a bit", "volume up"),
    ("make it a little louder", "volume up"),
    ("lock my computer now", "lock pc"),
    ("switch to the main branch", "switch branch to main"),
    ("tidy up my downloads folder", "organize downloads"),
]


@pytest.mark.parametrize("said,command", BLOCKED)
def test_unrelated_sentences_cannot_trigger_commands(said, command):
    assert not allowed_ai_command(said, command)


@pytest.mark.parametrize("said,command", ALLOWED)
def test_clear_requests_still_work(said, command):
    assert allowed_ai_command(said, command)
