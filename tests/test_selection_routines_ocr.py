"""Items 14, 15 and 17 (D37): selection commands, routines and the Windows OCR for read_screen.

Nothing real happens: the clipboard, the keyboard, the model and the screen are fakes, and the
routines file is in a temporary folder. The only real thing is Windows OCR on a picture drawn in
memory (silent, no screen capture), which is skipped where Windows has no OCR language.
"""
import pytest

from ultron import commands, paths  # noqa: F401  (commands registers every command)
from ultron import ocr
from ultron.commands import context, registry, router, routines, selection
from ultron.commands.router import Interaction

real = pytest.mark.real_handlers


# ---------------------------------------------------------------- a fake desktop
class Desktop:
    """Clipboard plus keyboard: Ctrl+C copies the selection, Ctrl+V pastes the clipboard."""

    def __init__(self, selected="", clipboard="my old clipboard", program="notepad.exe"):
        self.selected, self.clipboard, self.program = selected, clipboard, program
        self.keys, self.pasted = [], []

    def press(self, *keys):
        self.keys.append(keys)
        if keys == ("ctrl", "c") and self.selected:
            self.clipboard = self.selected
        elif keys == ("ctrl", "v"):
            self.pasted.append(self.clipboard)


@pytest.fixture
def desktop(monkeypatch):
    def make(**kw):
        d = Desktop(**kw)
        monkeypatch.setattr(selection, "_clip_get", lambda: d.clipboard)
        monkeypatch.setattr(selection, "_clip_set", lambda text: setattr(d, "clipboard", text))
        monkeypatch.setattr(selection, "_press", d.press)
        monkeypatch.setattr(selection, "foreground_program", lambda: d.program)
        monkeypatch.setattr(selection.time, "sleep", lambda s: None)
        return d
    return make


@pytest.fixture
def model(monkeypatch):
    """Records what the model was asked and answers with a canned reply."""
    seen = {"prompts": [], "reply": "A canned answer."}

    def fake_ask(prompt, max_tokens=200):
        seen["prompts"].append(prompt)
        return seen["reply"]
    monkeypatch.setattr(selection, "_ask", fake_ask)
    return seen


class Yes(Interaction):
    def __init__(self, approve=True):
        self.approve, self.prompts = approve, []

    def confirm(self, prompt):
        self.prompts.append(prompt)
        return self.approve


def say(text, io=None):
    return router.route(text, io or Interaction())


# ---------------------------------------------------------------- 14: the selection
@real
def test_grab_selection_returns_text_and_restores_the_clipboard(desktop):
    d = desktop(selected="Some highlighted words")
    assert selection.grab_selection() == "Some highlighted words"
    assert d.clipboard == "my old clipboard"
    assert d.keys == [("ctrl", "c")]


@real
def test_nothing_selected_is_said_honestly_and_the_clipboard_survives(desktop, model):
    d = desktop(selected="")
    outcome = say("explain this")
    assert outcome.reply == selection.NOTHING_SELECTED
    assert d.clipboard == "my old clipboard"
    assert model["prompts"] == []  # the model is never asked about nothing


@real
def test_selection_equal_to_the_old_clipboard_is_still_noticed(desktop, model):
    desktop(selected="same text", clipboard="same text")
    assert say("explain this").reply == "A canned answer."


@real
def test_terminals_never_get_ctrl_c(desktop, model):
    d = desktop(selected="x", program="windowsterminal.exe")
    reply = say("summarise this").reply
    assert "terminal" in reply and d.keys == []
    assert model["prompts"] == []


@real
@pytest.mark.parametrize("sentence, word", [
    ("explain this", "means"), ("what does this mean", "means"), ("summarise this", "Summarise"),
    ("tldr this", "Summarise"), ("explain the selected text", "means")])
def test_answering_commands_send_the_selection_to_the_model(desktop, model, sentence, word):
    d = desktop(selected="The mitochondria is the powerhouse of the cell.")
    outcome = say(sentence)
    assert outcome.reply == "A canned answer."
    assert "mitochondria" in model["prompts"][0] and word in model["prompts"][0]
    assert d.clipboard == "my old clipboard" and d.pasted == []


@real
def test_long_text_is_cut_for_explaining_but_refused_for_rewriting(desktop, model):
    desktop(selected="word " * 2000)  # 10000 characters
    assert say("explain this").reply == "A canned answer."
    assert len(model["prompts"][0]) < selection.READ_LIMIT + 300
    model["prompts"].clear()
    assert "too long" in say("make this more polite", Yes()).reply
    assert model["prompts"] == []


@real
def test_translate_speaks_latin_text(desktop, model):
    desktop(selected="Good morning")
    model["reply"] = "Bonjour"
    outcome = say("translate this to french")
    assert outcome.reply == "In French: Bonjour" and outcome.args == {"language": "french"}
    assert "French" in model["prompts"][0]


@real
def test_translate_to_a_script_the_voice_cannot_read_goes_to_the_clipboard(desktop, model):
    d = desktop(selected="Good morning")
    model["reply"] = "शुभ प्रभात"
    outcome = say("translate this to hindi")
    assert "clipboard" in outcome.reply and "शुभ" not in outcome.reply
    assert d.clipboard == "शुभ प्रभात"


@real
def test_translate_this_beats_the_plain_translate_command():
    with registry.dry_run():
        assert say("translate this to hindi").command == "translate_selection"
        assert say("translate good morning to spanish").command == "translate"


@real
def test_rewrite_pastes_only_after_a_spoken_confirm(desktop, model):
    d = desktop(selected="give me the report now")
    model["reply"] = "Could you please send me the report?"
    io = Yes(approve=True)
    outcome = say("make this more polite", io)
    assert outcome.reply == "Pasted."
    assert d.pasted == ["Could you please send me the report?"]
    assert d.clipboard == "my old clipboard"  # the user's own clipboard is back after the paste
    assert "Could you please send me the report?" in io.prompts[0] and "confirm" in io.prompts[0]
    assert "more polite" in model["prompts"][0]


@real
def test_rewrite_without_confirm_keeps_the_result_on_the_clipboard(desktop, model):
    d = desktop(selected="give me the report now")
    model["reply"] = "Could you please send me the report?"
    outcome = say("make this more polite", Yes(approve=False))
    assert "Not pasted" in outcome.reply and d.pasted == []
    assert d.clipboard == "Could you please send me the report?"


@real
def test_rewrite_with_the_default_interaction_never_pastes(desktop, model):
    d = desktop(selected="hello")
    say("proofread this")
    assert d.pasted == []


@real
def test_reply_uses_the_instruction_and_confirms(desktop, model):
    d = desktop(selected="Can you join the call at five?")
    model["reply"] = "Sorry, I will be late."
    outcome = say("reply to this saying i will be late", Yes())
    assert outcome.reply == "Pasted." and d.pasted == ["Sorry, I will be late."]
    assert "i will be late" in model["prompts"][0] and "join the call" in model["prompts"][0]


@real
def test_silent_model_is_reported(desktop, model):
    desktop(selected="hello there")
    model["reply"] = ""
    assert say("explain this").reply == selection.MODEL_SILENT
    assert say("reply to this", Yes()).reply == selection.MODEL_SILENT


def test_model_text_is_cleaned_for_the_voice():
    assert selection.clean_model_text('**Bold** and `code`') == "Bold and code"
    assert selection.clean_model_text('"quoted"') == "quoted"


@pytest.mark.parametrize("sentence, command", [
    ("explain this", "explain_selection"), ("what does this mean", "explain_selection"),
    ("translate this to hindi", "translate_selection"), ("summarise this", "summarise_selection"),
    ("make this more polite", "rewrite_selection"), ("reply to this", "reply_to_selection"),
    ("fix the grammar in this", "rewrite_selection"), ("turn this into bullet points", "rewrite_selection"),
    ("make this sound friendlier", "rewrite_selection"), ("draft a reply to this", "reply_to_selection")])
def test_selection_phrases_reach_their_command(sentence, command):
    assert say(sentence).command == command


@pytest.mark.parametrize("sentence", ["make it louder", "make this louder", "draft a reply saying i will be late",
                                      "explain this error", "summarise my day"])
def test_nearby_sentences_stay_with_their_own_commands(sentence):
    assert say(sentence).command not in {"rewrite_selection", "reply_to_selection", "explain_selection",
                                         "summarise_selection"}


# ---------------------------------------------------------------- 15: routines
@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ROUTINES_FILE", str(tmp_path / "data" / "routines.yaml"))
    context.clear()
    yield tmp_path / "data" / "routines.yaml"
    context.clear()


def test_history_records_what_was_said_but_not_routine_or_selection_commands(store):
    context.note_run("open_app", {"app": "chrome"}, "open chrome", "Opening Chrome.")
    context.note_run("explain_selection", {}, "explain this", "...")
    context.note_run("run_routine", {"name": "x"}, "run x routine", "...")
    context.note_run(None, None, "tell me a story", "once upon a time")
    assert list(context.history) == ["open chrome"]
    context.clear()
    assert list(context.history) == []


@real
def test_remember_saves_the_last_three_commands(store):
    for said in ("open vs code", "open chrome", "set the volume to 30", "flip a coin"):
        context.note_run("x", {}, said, "")
    reply = say("remember this as work mode").reply
    assert "Saved work mode with 3 steps" in reply
    assert routines.load() == {"work mode": ["open chrome", "set the volume to 30", "flip a coin"]}


@real
def test_remember_the_last_n_and_replace_an_old_routine(store):
    for said in ("open vs code", "open chrome", "set the volume to 30"):
        context.note_run("x", {}, said, "")
    say("remember the last 2 commands as work mode")
    assert routines.load()["work mode"] == ["open chrome", "set the volume to 30"]
    reply = say("remember the last 3 commands as my work routine").reply
    assert "replaces the old one" in reply
    assert list(routines.load()) == ["work mode"] and len(routines.load()["work mode"]) == 3


@real
def test_remember_with_nothing_to_record_says_so(store):
    assert "haven't run any commands" in say("remember this as work mode").reply
    assert not store.exists()


@real
def test_remember_this_as_a_name_is_not_saved_as_a_fact(store):
    from ultron.memory import facts
    before = list(facts.all())
    context.note_run("x", {}, "open chrome", "")
    say("remember this as chrome time")
    assert list(facts.all()) == before


@real
def test_run_routine_runs_every_step_in_order(store, monkeypatch):
    routines.save({"work mode": ["flip a coin", "roll a die"]})
    ran = []
    real_call = registry.call
    monkeypatch.setattr(registry, "call", lambda cmd, args: (ran.append(cmd.name), real_call(cmd, args))[1])
    monkeypatch.setattr(routines.time, "sleep", lambda s: None)
    for sentence in ("run work mode", "start my work routine", "run the work mode routine"):
        ran.clear()
        outcome = say(sentence)
        assert ran == ["run_routine", "flip_coin", "roll_die"], sentence
        assert outcome.reply == "Work mode is done. 2 steps."


@real
def test_a_step_that_is_not_understood_stops_the_routine(store, monkeypatch):
    routines.save({"odd": ["flip a coin", "blorp the frobnicator", "roll a die"]})
    ran = []
    real_call = registry.call
    monkeypatch.setattr(registry, "call", lambda cmd, args: (ran.append(cmd.name), real_call(cmd, args))[1])
    monkeypatch.setattr(routines.time, "sleep", lambda s: None)
    reply = say("run the odd routine").reply
    assert "stopped odd at step 2" in reply and "blorp the frobnicator" in reply
    assert "roll_die" not in ran


@real
def test_a_failing_step_stops_the_routine(store, monkeypatch):
    routines.save({"r": ["flip a coin", "roll a die"]})
    monkeypatch.setattr(routines.time, "sleep", lambda s: None)
    handler = registry.get("flip_coin").handler
    registry.get("flip_coin").handler = lambda: (_ for _ in ()).throw(RuntimeError("coin fell down a drain"))
    try:
        reply = say("run the r routine").reply
    finally:
        registry.get("flip_coin").handler = handler
    assert "stopped r at step 1" in reply and "coin fell down a drain" in reply


@real
def test_risky_steps_keep_their_confirm(store, monkeypatch):
    routines.save({"bye": ["roll a die", "shut down the computer"]})
    monkeypatch.setattr(routines.time, "sleep", lambda s: None)
    called = []
    monkeypatch.setattr("ultron.commands.risky.os.system", lambda cmd: called.append(cmd))
    io = Yes(approve=False)
    reply = say("run the bye routine", io).reply
    assert "stopped bye at step 2" in reply and "cancelled" in reply.lower()
    assert called == [] and len(io.prompts) == 1


@real
def test_a_routine_cannot_start_a_routine(store, monkeypatch):
    routines.save({"loop": ["run the loop routine"]})
    monkeypatch.setattr(routines.time, "sleep", lambda s: None)
    reply = say("run the loop routine").reply
    assert "stopped loop at step 1" in reply and "another routine" in reply


@real
def test_unknown_routine_is_said_and_unknown_mode_falls_through(store):
    routines.save({"gym": ["roll a die"]})
    reply = say("run the study routine").reply
    assert "don't have a routine called study" in reply and "gym" in reply
    assert say("start focus mode").command == "meeting_mode"  # an ordinary command, not a routine


@real
def test_list_and_mishearing(store):
    assert "no routines yet" in say("list my routines").reply
    routines.save({"work mode": ["flip a coin"], "gym": ["roll a die", "flip a coin"], "morning": ["roll a die"]})
    reply = say("what routines do i have").reply
    assert "work mode, 1 step" in reply and "gym, 2 steps" in reply
    assert routines.find("mornin", routines.load()) == "morning"
    assert routines.find("my gym routine", routines.load()) == "gym"
    assert routines.find("banana", routines.load()) is None


@real
def test_delete_needs_the_spoken_confirm(store):
    routines.save({"work mode": ["flip a coin"]})
    io = Yes(approve=False)
    from ultron import persona
    assert say("delete the work mode routine", io).reply in persona.CANCELLED_REPLIES
    assert "work mode" in routines.load()
    assert "work mode routine" in io.prompts[0].lower()
    assert say("delete the work mode routine", Yes(approve=True)).reply == "Deleted work mode."
    assert routines.load() == {}


@real
def test_a_broken_file_is_reported_not_overwritten(store):
    store.parent.mkdir(parents=True)
    store.write_text("work mode: [unclosed", encoding="utf-8")
    context.note_run("x", {}, "open chrome", "")
    assert "can't read your routines file" in say("remember this as w").reply
    assert store.read_text(encoding="utf-8") == "work mode: [unclosed"
    assert "can't read" in say("list my routines").reply


def test_the_example_file_loads_and_every_step_is_understood(monkeypatch):
    import yaml
    with open(paths.ROUTINES_EXAMPLE, encoding="utf-8") as f:
        example = yaml.safe_load(f)
    assert example and all(isinstance(s, list) and s for s in example.values())
    with registry.dry_run():
        for name, steps in example.items():
            for step in steps:
                assert say(step).command, f"{name}: {step!r} is not understood"


# ---------------------------------------------------------------- 17: Windows OCR
@pytest.fixture
def screen(monkeypatch):
    clip = {}
    monkeypatch.setattr("pyperclip.copy", lambda text: clip.update(text=text))
    state = {"text": "Invoice 4821\nTotal due: 120 dollars\nThanks", "window": object(), "screen": object(),
             "grabbed": []}
    monkeypatch.setattr(ocr, "grab_screen", lambda: state["grabbed"].append("screen") or state["screen"])
    monkeypatch.setattr(ocr, "grab_active_window", lambda: state["grabbed"].append("window") or state["window"])

    def fake_read(image):
        if isinstance(state["text"], Exception):
            raise state["text"]
        return state["text"]
    monkeypatch.setattr(ocr, "read_text", fake_read)
    return state, clip


@real
def test_read_screen_copies_the_text_and_speaks_a_short_summary(screen):
    state, clip = screen
    reply = say("read my screen").reply
    assert clip["text"] == state["text"]
    assert reply.startswith("Read 3 lines, copied to your clipboard.") and "Invoice 4821" in reply
    assert "Total due" not in reply  # only the first line is spoken
    assert state["grabbed"] == ["screen"]


@real
def test_read_window_reads_only_the_front_window(screen):
    state, clip = screen
    say("read this window")
    assert state["grabbed"] == ["window"] and clip["text"] == state["text"]


@real
def test_read_window_falls_back_to_the_screen(screen):
    state, _ = screen
    state["window"] = None
    say("read this window")
    assert state["grabbed"] == ["window", "screen"]


@real
def test_read_screen_with_no_text_or_no_ocr(screen):
    state, clip = screen
    state["text"] = ""
    assert "found no readable text" in say("read my screen").reply and "text" not in clip
    state["text"] = ocr.OcrUnavailable("Windows has no OCR language installed.")
    assert "no OCR language" in say("read my screen").reply


@real
def test_read_screen_never_writes_a_picture_to_disk(screen, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    say("read my screen")
    assert list(tmp_path.iterdir()) == []


def test_pytesseract_is_gone():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for f in [*(root / "src").rglob("*.py"), root / "pyproject.toml", root / "tests" / "requirements-ci.txt"]:
        assert "tesseract" not in f.read_text(encoding="utf-8").lower().replace("no tesseract", ""), f


def test_windows_ocr_reads_a_picture_drawn_in_memory():
    pytest.importorskip("winrt.windows.media.ocr")
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (700, 160), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 38)
    except OSError:
        pytest.skip("no Arial font to draw with")
    draw.text((20, 20), "Hello from the screen", fill="black", font=font)
    draw.text((20, 90), "Second line 12345", fill="black", font=font)
    try:
        text = ocr.read_text(image)
    except ocr.OcrUnavailable:
        pytest.skip("Windows has no OCR language installed")
    assert "Hello from the screen" in text and "12345" in text
