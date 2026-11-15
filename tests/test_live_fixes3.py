"""Fixes from the owner's live run on 2026-11-15 (15:00 to 15:06). Dry-run unless marked; nothing real runs."""
import pytest

from ultron import commands  # noqa: F401
from ultron.commands import apps, context, registry, router, slots, system
from ultron.commands.router import Interaction, Outcome, Reroute, execute, route, run_tool_call


class IO(Interaction):
    def __init__(self, answer=False):
        self.answer, self.prompts = answer, []

    def ask_yes_no(self, prompt):
        self.prompts.append(prompt)
        return self.answer

    def announce(self, text):
        return False


@pytest.fixture(autouse=True)
def fresh_context():
    context.clear()
    yield
    context.clear()


# ---- 9. optional slots are filled only from their own clause ----
@pytest.mark.parametrize("said", ["minimize all the windows", "minimise everything", "hide all my windows"])
def test_minimise_everything_keeps_nothing(said):
    out = route(said)
    assert out.command == "minimize_windows" and "keep" not in out.args, out


def test_keep_comes_only_from_an_except_clause():
    out = route("minimise everything except vs code")
    assert out.args.get("keep") == "vs code"
    cmd = registry.get("minimize_windows")
    assert "keep" not in slots.fill(cmd, "minimize all the windows")
    assert slots.fill(cmd, "minimize everything but chrome").get("keep") == "chrome"


def test_matcher_path_never_fills_keep_from_the_main_app():
    cmd = registry.get("minimize_windows")
    values = slots.fill(cmd, "get rid of all the windows")
    assert values.get("keep") is None or values.get("keep") != values.get("app")


# ---- 10. the answer to "Did you mean?" ----
def test_yes_runs_and_no_or_silence_cancels():
    cmd = registry.get("volume_up")
    assert "Would run volume_up" in execute(cmd, {}, IO(True), sure=False)
    for no in (False, ""):
        assert "Would run" not in execute(cmd, {}, IO(no), sure=False)  # cancelled, nothing ran


def test_other_answer_is_rerouted_as_a_new_sentence():
    cmd = registry.get("volume_up")
    with pytest.raises(Reroute) as e:
        execute(cmd, {}, IO("maximize everything"), sure=False)
    assert e.value.text == "maximize everything"


def test_route_routes_the_answer_once(monkeypatch):
    seen = []

    def fake(text, io, use_matcher):
        seen.append(text)
        if text == "maximize vs code":
            return Outcome("done", "rule", "maximize_window")
        raise Reroute("maximize vs code")

    monkeypatch.setattr(router, "_route", fake)
    out = route("maximise ability")
    assert out.reply == "done" and seen == ["maximise ability", "maximize vs code"]
    # an answer that asks yet another question is dropped, not chained
    monkeypatch.setattr(router, "_route", lambda t, i, u: (_ for _ in ()).throw(Reroute("again")))
    assert route("x").reply == ""


def test_tool_call_did_you_mean_answer_becomes_a_reroute_outcome():
    res = run_tool_call("volume_up", {}, ["volume_up"], IO("mute"), scores={"volume_up": 0.48}, sentence="make it louder")
    assert res.route == "reroute" and res.sentence == "mute" and res.reply is None


def test_repair_did_you_mean_answer_is_a_reroute_outcome():
    context.note_run("web_search", {"query": "base"}, "search base", "ok")
    # the answer to the retry offer is a new sentence, not yes or no
    out = router.repair("it isn't open", IO("open chrome"))
    assert out.route == "reroute" and out.sentence == "open chrome"


# ---- 11. misheard app names ----
FAKE_INDEX = {"claude": apps.APPS_FOLDER + "Claude_x!Claude", "visual studio code": r"C:\fake\Code.lnk",
              "obsidian": r"C:\fake\Obsidian.lnk"}


def test_window_commands_accept_sound_alike_names(monkeypatch):
    monkeypatch.setattr(apps, "start_menu_index", lambda: FAKE_INDEX)
    for name in ("close_app", "minimize_windows", "maximize_window"):
        cmd = registry.get(name)
        args = {"app": "clod"}
        assert router._apps_resolve(cmd, args), name
    assert not router._apps_resolve(registry.get("close_app"), {"app": "zzxqv"})


def test_hotwords_hold_apps_and_window_verbs(monkeypatch):
    monkeypatch.setattr(apps, "start_menu_index", lambda: FAKE_INDEX)
    words = apps.hotword_names()
    assert "VS Code" in words and "maximize" in words and "Obsidian" in words


# ---- 12. folders: "New folder (2)" and rename ----
@pytest.mark.real_handlers
def test_unnamed_folder_gets_windows_numbering_and_rename_works(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Desktop").mkdir()
    assert "New folder in" in system.create_folder()
    assert "New folder (2) in" in system.create_folder()
    assert (tmp_path / "Desktop" / "New folder (2)").is_dir()
    assert context.created_folder == str(tmp_path / "Desktop" / "New folder (2)")
    assert system.rename_item() == "What should I call it?" and context.pending == "rename_name"
    assert system.rename_item("cast") == "Renamed it to cast."
    assert (tmp_path / "Desktop" / "cast").is_dir() and context.created_folder.endswith("cast")
    assert "already exists" in system.rename_item("New folder")
    assert "usable" in system.rename_item("???")


@pytest.mark.real_handlers
def test_rename_refuses_paths_outside_the_user_folders(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    context.note_folder(str(outside))
    assert "outside" in system.rename_item("x") and outside.is_dir()
    context.note_folder(str(home))  # the profile folder itself is not renamable either
    assert "outside" in system.rename_item("x")
    context.clear()
    assert "haven't created" in system.rename_item("x")


def test_rename_phrases_and_the_name_answer():
    assert route("rename it").command == "rename_item"
    out = route("rename it to invoices")
    assert out.command == "rename_item" and out.args == {"name": "invoices"}
    context.pending = "rename_name"
    out = route("Invoices 2024.")
    assert out.command == "rename_item" and out.args == {"name": "Invoices 2024"}
    context.pending = "rename_name"
    assert route("never mind").command != "rename_item"
    assert context.pending is None


def test_open_the_folder_you_just_created():
    assert route("open the folder you just created.").command == "open_folder"
