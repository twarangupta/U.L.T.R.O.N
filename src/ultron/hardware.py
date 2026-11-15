"""Pick models and settings that fit this PC.

ULTRON looks at the machine once at startup (RAM, CPU cores, NVIDIA GPU and
its memory) and chooses a profile:

    Lite        no usable NVIDIA GPU, under 16 GB RAM or few cores
    CPU-Plus    no usable NVIDIA GPU, 16 GB+ RAM and 8+ cores
    GPU-4GB     NVIDIA GPU with 4 to 7 GB of VRAM
    GPU-8GB+    NVIDIA GPU with 8 to 15 GB
    GPU-16GB+   NVIDIA GPU with 16 GB or more

Rules:
- The LLM gets the GPU first. Whisper goes on the GPU only if the VRAM left
  after the LLM (and a reserve for Windows) still fits it.
- Strong PCs get bigger models; weak PCs never get more than they can hold.
- Every choice can be overridden with an environment variable (see
  ENV_OVERRIDES below), and ULTRON_PROFILE forces a profile by name.
- The GPU is only used if CUDA really works; stt.py falls back to the CPU on
  any GPU error.

This module only decides. Loading the models happens in stt.py and brain.py.
"""
from __future__ import annotations

import ctypes
import glob
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from ultron.logger import logger

GB = 1024 ** 3

# VRAM kept free for Windows, the browser and the display (GB).
VRAM_RESERVE_GB = 0.5
# Extra VRAM an Ollama model needs on top of its file size (context, buffers).
LLM_VRAM_OVERHEAD_GB = 0.8

# Approximate VRAM (GB) a Whisper model needs on the GPU, by compute type.
WHISPER_VRAM_GB = {
    "tiny": 0.25, "base": 0.35, "small": 0.7, "medium": 1.6,
    "large-v3-turbo": 1.7, "large-v3": 3.2,
}
INT8_VRAM_FACTOR = 0.6  # int8_float16 needs roughly 60 percent of float16

# Approximate file size (GB) of LLMs we may pick, for when Ollama cannot tell us.
LLM_SIZE_GB = {
    "llama3.2:1b": 1.3, "llama3.2:3b": 2.0, "qwen2.5:3b": 1.9, "gemma3:4b": 3.3,
    "llama3.1:8b": 4.9, "qwen3:8b": 5.2, "gemma3:12b": 8.1, "qwen3:14b": 9.3,
}


@dataclass
class Hardware:
    ram_gb: float
    physical_cores: int
    logical_cores: int
    gpu_name: str | None = None
    vram_total_gb: float = 0.0
    driver: str | None = None

    @property
    def has_nvidia(self) -> bool:
        return self.gpu_name is not None


@dataclass
class Profile:
    name: str
    whisper_model: str
    whisper_device: str            # "cuda" or "cpu"
    whisper_compute_type: str
    whisper_cpu_threads: int
    llm_model: str
    llm_candidates: list[str]      # best first; the first installed one is used
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"profile={self.name} whisper={self.whisper_model} on {self.whisper_device} "
            f"({self.whisper_compute_type}, {self.whisper_cpu_threads} threads) llm={self.llm_model}"
        )


# Profile defaults. Whisper and LLM picks here are the starting point; the
# VRAM budget below may still move Whisper to the CPU.
PROFILES = {
    "Lite": dict(
        whisper=("base", "int8"), whisper_gpu=None,
        llm=["qwen2.5:3b", "llama3.2:3b", "llama3.2:1b"],
    ),
    # gemma3 is left out everywhere: Ollama rejects tool calls for it (D30),
    # so it cannot pick commands.
    "CPU-Plus": dict(
        whisper=("small", "int8"), whisper_gpu=None,
        llm=["qwen2.5:3b", "llama3.2:3b"],
    ),
    "GPU-4GB": dict(
        whisper=("base", "int8"), whisper_gpu=("small", "int8_float16"),
        llm=["qwen2.5:3b", "llama3.2:3b", "llama3.2:1b"],  # D30: fewest wrong tool calls (BUILD_LOG)
    ),
    "GPU-8GB+": dict(
        whisper=("small", "int8"), whisper_gpu=("large-v3-turbo", "int8_float16"),
        llm=["llama3.1:8b", "qwen3:8b", "qwen2.5:3b", "llama3.2:3b"],
    ),
    "GPU-16GB+": dict(
        whisper=("small", "int8"), whisper_gpu=("large-v3-turbo", "float16"),
        llm=["qwen3:14b", "llama3.1:8b", "qwen3:8b", "qwen2.5:3b", "llama3.2:3b"],
    ),
}

ENV_OVERRIDES = {
    "ULTRON_PROFILE": "force a profile: Lite, CPU-Plus, GPU-4GB, GPU-8GB+, GPU-16GB+",
    "WHISPER_MODEL_SIZE": "Whisper model name or folder",
    "WHISPER_DEVICE": "cpu or cuda",
    "WHISPER_COMPUTE_TYPE": "int8, int8_float16, float16, float32",
    "WHISPER_CPU_THREADS": "CPU threads for Whisper",
    "OLLAMA_MODEL": "LLM model name in Ollama",
}


# Detection -----------------------------------------------------------------

def detect_hardware() -> Hardware:
    import psutil

    hw = Hardware(
        ram_gb=psutil.virtual_memory().total / GB,
        physical_cores=psutil.cpu_count(logical=False) or 1,
        logical_cores=psutil.cpu_count(logical=True) or 1,
    )
    gpu = _query_nvidia_smi()
    if gpu:
        hw.gpu_name, hw.vram_total_gb, hw.driver = gpu
    return hw


def _query_nvidia_smi():
    """(name, total VRAM in GB, driver) of the first NVIDIA GPU, or None."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
        name, mem_mib, driver = [part.strip() for part in out.splitlines()[0].split(",")]
        return name, float(mem_mib) / 1024, driver
    except Exception as e:
        logger.debug(f"nvidia-smi query failed: {e}")
        return None


def add_cuda_dll_paths() -> list[str]:
    """Let ctranslate2 find the CUDA libraries from the nvidia-* pip wheels.

    The wheels put their DLLs in site-packages/nvidia/<lib>/bin, which Windows
    does not search by default. Must run before ctranslate2 loads them.
    """
    found = []
    for site in sys.path:
        found += glob.glob(os.path.join(site, "nvidia", "*", "bin"))
    for path in found:
        try:
            os.add_dll_directory(path)
        except (OSError, AttributeError):
            pass
    if found:
        # cuDNN loads its sub-libraries with plain LoadLibrary, which reads PATH.
        os.environ["PATH"] = os.pathsep.join(found + [os.environ.get("PATH", "")])
    return found


def cuda_libraries_present() -> tuple[bool, str]:
    """Quick check that ctranslate2 sees a GPU and the CUDA DLLs load.

    The real proof is loading Whisper on the GPU, which stt.py does (and falls
    back to the CPU if it fails). This check avoids even trying when the
    libraries are plainly missing.
    """
    add_cuda_dll_paths()
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() < 1:
            return False, "ctranslate2 sees no CUDA device"
    except Exception as e:
        return False, f"ctranslate2 failed: {e}"
    if sys.platform == "win32":
        # Whisper in ctranslate2 needs only cuBLAS (measured: cuDNN is never loaded).
        for dll in ("cublas64_12.dll", "cublasLt64_12.dll"):
            try:
                ctypes.WinDLL(dll)
            except OSError:
                return False, f"{dll} not found (install requirements-gpu.txt)"
    return True, "CUDA libraries load"


def installed_ollama_models() -> dict[str, float]:
    """Installed Ollama models and their sizes in GB. Empty if Ollama is down."""
    try:
        import ollama
        return {m.model: (m.size or 0) / GB for m in ollama.list().models}
    except Exception as e:
        logger.debug(f"Could not list Ollama models: {e}")
        return {}


# Choosing ------------------------------------------------------------------

def profile_name_for(hw: Hardware) -> str:
    if hw.has_nvidia and hw.vram_total_gb >= 15.5:
        return "GPU-16GB+"
    if hw.has_nvidia and hw.vram_total_gb >= 7.5:
        return "GPU-8GB+"
    if hw.has_nvidia and hw.vram_total_gb >= 3.5:
        return "GPU-4GB"
    if hw.ram_gb >= 15 and hw.physical_cores >= 8:
        return "CPU-Plus"
    return "Lite"


def _same_model(a: str, b: str) -> bool:
    """'llama3.2:3b' matches 'llama3.2:3b'; 'gemma3' matches 'gemma3:latest'."""
    def norm(name):
        return name if ":" in name else name + ":latest"
    return norm(a) == norm(b)


def pick_llm(candidates: list[str], installed: dict[str, float]) -> tuple[str, str]:
    """First candidate that is installed, else the first candidate. Returns (model, reason)."""
    for name in candidates:
        if any(_same_model(name, have) for have in installed):
            return name, f"LLM {name} is the best installed model for this profile"
    if not installed:
        return candidates[0], f"LLM {candidates[0]} (Ollama not reachable, cannot check what is installed)"
    return candidates[0], f"LLM {candidates[0]} is not installed: run 'ollama pull {candidates[0]}'"


def llm_vram_gb(model: str, installed: dict[str, float]) -> float:
    size = next((gb for have, gb in installed.items() if _same_model(model, have)), None)
    if size is None:
        size = LLM_SIZE_GB.get(model, 3.0)
    return size + LLM_VRAM_OVERHEAD_GB


def whisper_vram_gb(model: str, compute_type: str) -> float:
    base = next((gb for key, gb in WHISPER_VRAM_GB.items() if model.startswith(key)), 1.0)
    return base * (INT8_VRAM_FACTOR if compute_type.startswith("int8") else 1.0)


def choose_profile(hw: Hardware, env=os.environ, installed=None, cuda_check=cuda_libraries_present) -> Profile:
    """Build the profile for this machine. Pure apart from cuda_check and Ollama."""
    reasons = []
    name = env.get("ULTRON_PROFILE") or profile_name_for(hw)
    if name not in PROFILES:
        reasons.append(f"Unknown ULTRON_PROFILE {name!r}, using auto-detect")
        name = profile_name_for(hw)
    elif env.get("ULTRON_PROFILE"):
        reasons.append(f"Profile forced by ULTRON_PROFILE={name}")
    spec = PROFILES[name]

    if installed is None:
        installed = installed_ollama_models()
    llm, why = pick_llm(spec["llm"], installed)
    reasons.append(why)
    if env.get("OLLAMA_MODEL"):
        llm = env["OLLAMA_MODEL"]
        reasons.append(f"LLM forced by OLLAMA_MODEL={llm}")

    whisper, compute = spec["whisper"]
    device = "cpu"
    if spec["whisper_gpu"]:
        gpu_whisper, gpu_compute = spec["whisper_gpu"]
        room = hw.vram_total_gb - VRAM_RESERVE_GB - llm_vram_gb(llm, installed)
        need = whisper_vram_gb(gpu_whisper, gpu_compute)
        if room < need:
            # The LLM keeps the GPU; try the smaller CPU-default model on the GPU before giving up.
            cpu_need = whisper_vram_gb(whisper, "int8_float16")
            if room >= cpu_need:
                gpu_whisper, gpu_compute, need = whisper, "int8_float16", cpu_need
        if room >= need:
            ok, why = cuda_check()
            if ok:
                whisper, compute, device = gpu_whisper, gpu_compute, "cuda"
                reasons.append(f"Whisper on GPU: {need:.1f} GB fits in {room:.1f} GB left after the LLM")
            else:
                reasons.append(f"Whisper on CPU: {why}")
        else:
            reasons.append(f"Whisper on CPU: only {max(room, 0):.1f} GB VRAM left after the LLM, needs {need:.1f}")

    threads = max(1, min(hw.physical_cores, 8))

    # Manual overrides win over everything.
    if env.get("WHISPER_MODEL_SIZE"):
        whisper = env["WHISPER_MODEL_SIZE"]
        reasons.append(f"Whisper model forced by WHISPER_MODEL_SIZE={whisper}")
    if env.get("WHISPER_DEVICE"):
        device = env["WHISPER_DEVICE"].lower()
        reasons.append(f"Whisper device forced by WHISPER_DEVICE={device}")
        if device == "cuda":
            add_cuda_dll_paths()
    if env.get("WHISPER_COMPUTE_TYPE"):
        compute = env["WHISPER_COMPUTE_TYPE"]
    elif device == "cpu" and compute not in ("int8", "float32", "int8_float32"):
        compute = "int8"
    elif device == "cuda" and compute == "int8":
        compute = "int8_float16"
    if env.get("WHISPER_CPU_THREADS"):
        threads = int(env["WHISPER_CPU_THREADS"])

    return Profile(
        name=name, whisper_model=whisper, whisper_device=device,
        whisper_compute_type=compute, whisper_cpu_threads=threads,
        llm_model=llm, llm_candidates=list(spec["llm"]), reasons=reasons,
    )


def describe(hw: Hardware) -> str:
    gpu = f"{hw.gpu_name}, {hw.vram_total_gb:.1f} GB VRAM, driver {hw.driver}" if hw.has_nvidia else "no NVIDIA GPU"
    return f"{hw.ram_gb:.1f} GB RAM, {hw.physical_cores} cores / {hw.logical_cores} threads, {gpu}"


_profile: Profile | None = None


def get_profile() -> Profile:
    """Detect once per run and log the result."""
    global _profile
    if _profile is None:
        from ultron import config  # noqa: F401  (loads .env so its overrides count)
        hw = detect_hardware()
        _profile = choose_profile(hw)
        logger.info(f"Hardware: {describe(hw)}")
        logger.info(f"Hardware profile: {_profile.summary()}")
        for reason in _profile.reasons:
            logger.info(f"  {reason}")
    return _profile
