"""Voice file choice: default, named, path, and the fallback when the chosen voice is missing."""
import os

from ultron.voice.voice_files import model_paths, pick_model


def test_default_is_joe_then_legacy():
    paths = model_paths("en_US-joe-medium")
    assert paths[0].endswith(os.path.join("voices", "en_US-joe-medium.onnx"))
    assert paths[1].endswith("ultron-voice.onnx")


def test_empty_name_means_legacy_only_and_paths_pass_through():
    assert model_paths("")[0].endswith("ultron-voice.onnx")
    assert model_paths("C:/x/custom.onnx")[0] == "C:/x/custom.onnx"


def test_missing_first_choice_warns_and_falls_back(tmp_path, caplog):
    old = tmp_path / "old.onnx"
    old.write_bytes(b"x")
    with caplog.at_level("WARNING"):
        assert pick_model([str(tmp_path / "joe.onnx"), str(old)]) == str(old)
    text = caplog.text
    assert "download_voice.py joe" in text and "old.onnx" in text


def test_nothing_found_returns_none_without_crashing(tmp_path):
    assert pick_model([str(tmp_path / "a.onnx"), str(tmp_path / "b.onnx")]) is None
