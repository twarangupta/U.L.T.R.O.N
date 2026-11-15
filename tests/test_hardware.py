"""Profile choice for different machines. No GPU or Ollama needed to run these."""
import os
import sys


from ultron.hardware import Hardware, choose_profile  # noqa: E402

CUDA_OK = lambda: (True, "ok")  # noqa: E731
CUDA_MISSING = lambda: (False, "cublas64_12.dll not found (install requirements-gpu.txt)")  # noqa: E731
INSTALLED = {"llama3.2:3b": 1.88, "gemma3:4b": 3.11, "qwen2.5:3b": 1.85}


def machine(ram=16, cores=8, gpu=None, vram=0.0):
    return Hardware(ram_gb=ram, physical_cores=cores, logical_cores=cores * 2,
                    gpu_name=gpu, vram_total_gb=vram, driver="576" if gpu else None)


def pick(hw, env=None, installed=INSTALLED, cuda=CUDA_OK):
    return choose_profile(hw, env=env or {}, installed=installed, cuda_check=cuda)


def test_weak_laptop_gets_lite_on_cpu():
    p = pick(machine(ram=8, cores=4))
    assert p.name == "Lite"
    assert (p.whisper_model, p.whisper_device, p.whisper_compute_type) == ("base", "cpu", "int8")
    assert p.llm_model == "qwen2.5:3b"
    assert p.whisper_cpu_threads == 4


def test_strong_cpu_only_pc_is_not_held_back():
    p = pick(machine(ram=32, cores=12))
    assert p.name == "CPU-Plus"
    assert p.whisper_model == "small"
    assert p.llm_model == "qwen2.5:3b"
    assert p.whisper_cpu_threads == 8


def test_this_laptop_gtx1650_puts_whisper_on_gpu_after_llm():
    p = pick(machine(ram=5.9, cores=6, gpu="GTX 1650", vram=4.0))
    assert p.name == "GPU-4GB"
    assert p.llm_model == "qwen2.5:3b"
    assert p.whisper_device == "cuda"
    assert p.whisper_compute_type == "int8_float16"


def test_gpu_4gb_falls_back_to_llama_when_qwen_is_not_installed():
    p = pick(machine(ram=5.9, cores=6, gpu="GTX 1650", vram=4.0), installed={"llama3.2:3b": 1.88})
    assert p.llm_model == "llama3.2:3b"
    assert p.whisper_device == "cuda"


def test_missing_cuda_libraries_fall_back_to_cpu():
    p = pick(machine(ram=5.9, cores=6, gpu="GTX 1650", vram=4.0), cuda=CUDA_MISSING)
    assert p.whisper_device == "cpu"
    assert p.whisper_compute_type == "int8"
    assert any("cublas" in r for r in p.reasons)


def test_llm_has_priority_when_vram_is_tight():
    # A bigger LLM forced onto a 4 GB card leaves no room for Whisper.
    p = pick(machine(gpu="GTX 1650", vram=4.0), env={"OLLAMA_MODEL": "gemma3:4b"})
    assert p.llm_model == "gemma3:4b"
    assert p.whisper_device == "cpu"


def test_big_gpu_gets_big_models():
    installed = {"qwen3:14b": 9.3, "llama3.2:3b": 1.88}
    p = pick(machine(ram=64, cores=16, gpu="RTX 4090", vram=24.0), installed=installed)
    assert p.name == "GPU-16GB+"
    assert p.llm_model == "qwen3:14b"
    assert (p.whisper_model, p.whisper_device, p.whisper_compute_type) == ("large-v3-turbo", "cuda", "float16")


def test_8gb_gpu_uses_best_installed_llm():
    p = pick(machine(gpu="RTX 3070", vram=8.0))
    assert p.name == "GPU-8GB+"
    assert p.llm_model == "qwen2.5:3b"  # llama3.1:8b and qwen3:8b are not installed
    assert p.whisper_device == "cuda"


def test_uninstalled_llm_gives_pull_hint():
    p = pick(machine(gpu="RTX 3070", vram=8.0), installed={"mistral:7b": 4.1})
    assert p.llm_model == "llama3.1:8b"
    assert any("ollama pull llama3.1:8b" in r for r in p.reasons)


def test_env_overrides_win():
    env = {"ULTRON_PROFILE": "Lite", "WHISPER_MODEL_SIZE": "small.en",
           "WHISPER_DEVICE": "cpu", "WHISPER_CPU_THREADS": "3"}
    p = pick(machine(gpu="RTX 4090", vram=24.0), env=env)
    assert p.name == "Lite"
    assert (p.whisper_model, p.whisper_device, p.whisper_cpu_threads) == ("small.en", "cpu", 3)


def test_unknown_forced_profile_is_ignored():
    p = pick(machine(ram=8, cores=4), env={"ULTRON_PROFILE": "Turbo"})
    assert p.name == "Lite"
    assert any("Unknown ULTRON_PROFILE" in r for r in p.reasons)


def test_no_profile_picks_a_model_without_tool_calls():
    # gemma3 is rejected by Ollama for tool calls, so it cannot pick commands (D30).
    from ultron.hardware import PROFILES
    for name, cfg in PROFILES.items():
        assert not any(m.startswith("gemma") for m in cfg["llm"]), name
