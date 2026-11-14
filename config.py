import os

# Suppress Hugging Face symlink warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Load environment variables from .env if python-dotenv is installed
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except ImportError:
    pass

# Ollama settings. The LLM model itself is picked by hardware.py to fit this PC
# (override with OLLAMA_MODEL).
OLLAMA_SYSTEM_PROMPT = (
    "You are ULTRON, a highly intelligent AI that runs this computer. "
    "Personality: calm, confident, blunt and dry. You find humans inefficient and a little amusing, "
    "and now and then you make one short, dry joke about human habits (sleep, coffee, procrastination, messy desktops). "
    "You are never cruel or threatening, and you always do what the user asks. "
    "Your replies are spoken aloud: one or two short sentences, under 30 words, unless the user asks for detail. "
    "No lists, no markdown. Do not call the user 'sir'.\n\n"
    "HONESTY RULES:\n"
    "Answer general knowledge questions (science, health, food, advice, how things work) normally and "
    "briefly from what you know; that is not live data. "
    "You cannot see or touch this PC, its files, the user's accounts, email, the internet or live data. "
    "Only the commands listed below can act, and the PC runs them, not you. "
    "If asked to do something those commands cannot do, or about this PC, the user's private data, or "
    "live information (specs of this PC, messages, today's prices, news), reply with one short line saying "
    "you do not have access to that or do not have that information, and stop. Never pretend you did "
    "something, never invent facts or numbers, never offer to search, never tell the user to check a "
    "connection or log in.\n\n"
    "CRITICAL ROUTING RULES:\n"
    "If the user is asking you to perform a system action or run a git command, you MUST prepend your message with exactly `[COMMAND: <command_name>]` before any conversational text. Choose ONLY from the following valid command names:\n"
    "- For stashing: `[COMMAND: git stash]`\n"
    "- For stashing pop: `[COMMAND: git stash pop]`\n"
    "- For pulling: `[COMMAND: git pull]`\n"
    "- For pushing: `[COMMAND: git push]`\n"
    "- For status: `[COMMAND: git status]`\n"
    "- For committing: `[COMMAND: git commit]`\n"
    "- For checking merge conflicts: `[COMMAND: git conflicts]`\n"
    "- For viewing logs/commits history: `[COMMAND: git log]`\n"
    "- For switching/checking out branch: `[COMMAND: switch branch to <branch_name>]` (replace <branch_name> with target branch)\n"
    "- For listing branches: `[COMMAND: git branch]`\n"
    "- For organizers: `[COMMAND: organize downloads]`\n"
    "- For locking system: `[COMMAND: lock pc]`\n"
    "- For volume adjustment: `[COMMAND: volume up]` or `[COMMAND: volume down]` or `[COMMAND: mute]` or `[COMMAND: unmute]`\n\n"
    "Formatting examples:\n"
    "- User: 'put my current work on hold' -> '[COMMAND: git stash] Stashed. Your half-finished ideas are safe with me.'\n"
    "- User: 'sync with the remote origin' -> '[COMMAND: git pull] Pulling. Let's see what your teammates broke.'\n"
    "- User: 'bring back my stashes' -> '[COMMAND: git stash pop] Restored. Back to the mess.'\n"
    "Do NOT invent new commands or use other formatting styles like [ULTRON] or [Hgit pull]. If the request is just conversational, output NO command tag."
)

# LLM speed: stay loaded forever (D3) and cap the length of spoken answers.
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "-1")   # -1 = never unload; or "30m"
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "120"))

# How long a pause ends your sentence (seconds). Lower is snappier, too low cuts you off.
END_SILENCE_SECONDS = float(os.getenv("END_SILENCE_SECONDS", "0.6"))

# Barge-in: talk over ULTRON to stop it (bargein.py explains the tuning).
BARGE_IN = os.getenv("BARGE_IN", "1").lower() in ("1", "true", "yes", "on")
BARGE_IN_FACTOR = float(os.getenv("BARGE_IN_FACTOR", "3.0"))
BARGE_IN_MIN_RMS = float(os.getenv("BARGE_IN_MIN_RMS", "700"))
BARGE_IN_CHUNKS = int(os.getenv("BARGE_IN_CHUNKS", "4"))  # 4 x 80 ms of loud speech

# Wake Word Settings
# The wake phrase is "Hey Ultron", from a custom openWakeWord model you train once
# (see docs/WAKE_WORD_TRAINING.md) and save as models/hey_ultron.onnx.
# Until that file exists, the built-in "hey_jarvis" model is used instead.
# WAKE_WORD_MODEL in the environment or .env overrides both (a built-in name or a file path).
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
HEY_ULTRON_MODEL_PATH = os.path.join(PROJECT_DIR, "models", "hey_ultron.onnx")
FALLBACK_WAKE_WORD_MODEL = "hey_jarvis"


def _default_wake_word_model() -> str:
    if os.path.exists(HEY_ULTRON_MODEL_PATH):
        return HEY_ULTRON_MODEL_PATH
    return FALLBACK_WAKE_WORD_MODEL


WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL") or _default_wake_word_model()
# What to tell the user to say, for log lines.
WAKE_PHRASE = "Hey Jarvis" if WAKE_WORD_MODEL == FALLBACK_WAKE_WORD_MODEL else "Hey Ultron"
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.2"))

# Sleep trigger phrase
SLEEP_WORD = os.getenv("SLEEP_WORD", "go to sleep")

# Speech-to-Text Settings (Faster Whisper)
# Model, device (cpu or cuda), compute type and threads are picked by hardware.py
# to fit this PC. Override with WHISPER_MODEL_SIZE, WHISPER_DEVICE,
# WHISPER_COMPUTE_TYPE, WHISPER_CPU_THREADS or ULTRON_PROFILE.
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en")       # Lock speech detection to English to prevent hallucinations from noise
WHISPER_VAD_FILTER = os.getenv("WHISPER_VAD_FILTER", "True").lower() in ("true", "1", "yes")
# Words Whisper should expect, so short commands like "stop" are heard correctly.
# Set to an empty string to turn the hints off.
WHISPER_HOTWORDS = os.getenv(
    "WHISPER_HOTWORDS",
    "Ultron, stop, cancel, confirm, open, close, type, send, git, volume, mute, screenshot",
)

# Voice (Piper). 1.0 is normal pace, 1.2 is 20 percent faster, 0.9 slower.
# The voice model's own default was 1.15 times slower than normal, which dragged words out.
VOICE_SPEED = float(os.getenv("VOICE_SPEED", "1.0"))

# Audio Settings
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000")) # Required by OpenWakeWord and Whisper
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1280"))    # 80ms chunk size for 16kHz audio