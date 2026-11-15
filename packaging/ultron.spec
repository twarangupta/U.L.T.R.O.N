# PyInstaller spec for ULTRON. Build with packaging/build.ps1 (or: pyinstaller packaging/ultron.spec).
#
# onedir, not onefile: a onefile exe unpacks itself to a temp folder on every start (adds seconds, which
# fights the "feels instant" goal) and its self-extracting stub is what antivirus products flag most often.
# The cost: the output is a folder (dist/ULTRON/), so the real installer (Inno Setup) has to wrap it.
#
# NOT bundled on purpose:
#   models/        downloaded by the first-run wizard with live progress (D25)
#   CUDA libraries nvidia-cublas-cu12, nvidia-cudnn-cu12, nvidia-cuda-nvrtc-cu12 (about 1.5 GB). They become a
#                  separate "GPU pack" downloaded only on NVIDIA machines (D24). Without it Whisper runs on the CPU.
#   Tesseract      the OCR item [17] will use Windows' built-in OCR instead.
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.dirname(SPECPATH)

datas, binaries, hiddenimports = [], [], []

# Libraries with native DLLs, data files or imports made at run time, which static analysis cannot see.
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "openwakeword", "piper", "model2vec", "av"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

# Windows COM and WinRT. comtypes builds wrappers in comtypes.gen at run time; pycaw and winrt import lazily.
for pkg in ("comtypes", "pycaw", "winrt", "pythoncom", "win32com"):
    hiddenimports += collect_submodules(pkg)
datas += collect_data_files("pyaudio") + collect_data_files("sounddevice")
hiddenimports += ["win32com.client", "sounddevice", "pyaudio"]

# The command modules are imported by name from ultron/commands/__init__.py; list the whole package.
hiddenimports += collect_submodules("ultron")

# User-editable settings ship as data. paths.py looks for config/ next to the program (see build.ps1).
datas += [(os.path.join(ROOT, "config"), "config")]

# Excluded: the CUDA runtime (GPU pack, D24) and big libraries ULTRON never imports.
EXCLUDES = [
    "nvidia", "nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc",
    "tkinter", "matplotlib", "pandas", "PIL.ImageTk", "IPython", "pytest", "ruff", "vulture", "setuptools",
    "torch", "tensorflow", "sympy", "numba",
]

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=EXCLUDES,
    noarchive=False,
)

# Belt and braces: drop any CUDA DLL that a hook pulled in anyway.
CUDA_DLL_PREFIXES = ("cublas", "cublaslt", "cudnn", "nvrtc", "cudart", "cufft", "curand", "cusparse", "cusolver")
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).lower().startswith(CUDA_DLL_PREFIXES)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ULTRON", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ULTRON", upx=False)
