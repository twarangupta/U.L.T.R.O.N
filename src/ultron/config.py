"""Settings read from the environment or a .env file at the project root, with their defaults.

Also holds the LLM system prompt (the honesty rules). Paths are not here: see paths.py."""

import os

from ultron import paths

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
    "Only the tools you are given can act, and the PC runs them, not you. "
    "If asked to do something no tool can do, or about this PC, the user's private data, or "
    "live information (specs of this PC, messages, today's prices, news), reply with one short line saying "
    "you do not have access to that or do not have that information, and stop. Never pretend you did "
    "something, never invent facts or numbers, never offer to search, never tell the user to check a "
    "connection or log in.\n\n"
    "TOOLS: when tools are offered, call one only if the user is clearly asking you to do that action now. "
    "For questions, chat, advice, or anything the tools do not do, answer in words and call no tool. "
    "Never describe a tool call in text."
)

# LLM speed: stay loaded forever (D3) and cap the length of spoken answers.
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "-1")   # -1 = never unload; or "30m"
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "120"))

# How long a pause ends your sentence (seconds). Lower is snappier, too low cuts you off.
# END_SILENCE_SECONDS is for the fallback (loudness check, used only when the VAD model is missing);
# VAD_END_SILENCE_SECONDS is for Silero VAD, which tells speech from noise and so can wait less.
END_SILENCE_SECONDS = float(os.getenv("END_SILENCE_SECONDS", "0.6"))
VAD_END_SILENCE_SECONDS = float(os.getenv("VAD_END_SILENCE_SECONDS", "0.35"))
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))   # speech probability from 0 to 1; higher = stricter
VAD_BARGE_IN = os.getenv("VAD_BARGE_IN", "1").lower() in ("1", "true", "yes", "on")  # barge-in also needs speech, not just loudness

# After this many seconds in a conversation with no recognised speech, ULTRON says a line and
# goes back to waiting for the wake word. 0 turns it off.
CONVERSATION_IDLE_SECONDS = float(os.getenv("CONVERSATION_IDLE_SECONDS", "45"))

# Barge-in: talk over ULTRON to stop it (bargein.py explains the tuning).
BARGE_IN = os.getenv("BARGE_IN", "1").lower() in ("1", "true", "yes", "on")
BARGE_IN_FACTOR = float(os.getenv("BARGE_IN_FACTOR", "3.0"))
# 200: the measured echo of ULTRON's own voice is 0 to 8 RMS (x3 = under 25), so a 700 floor never let
# normal speech through; 200 still sits well above room noise. The "speech level" log line shows your real level.
BARGE_IN_MIN_RMS = float(os.getenv("BARGE_IN_MIN_RMS", "200"))
BARGE_IN_CHUNKS = int(os.getenv("BARGE_IN_CHUNKS", "4"))  # 4 x 80 ms of loud speech

# Wake Word Settings
# The wake phrase is "Hey Ultron", from a custom openWakeWord model you train once
# (see docs/WAKE_WORD_TRAINING.md) and save as models/hey_ultron.onnx.
# Until that file exists, the built-in "hey_jarvis" model is used instead.
# WAKE_WORD_MODEL in the environment or .env overrides both (a built-in name or a file path).
HEY_ULTRON_MODEL_PATH = os.path.join(paths.MODELS_DIR, "hey_ultron.onnx")
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
# Whisper retries unclear audio at higher temperatures, which cost up to 2.1 s on one command.
# Off by default (temperature 0 only: one pass). Set to 1 to bring the retries back.
WHISPER_TEMPERATURE_FALLBACK = os.getenv("WHISPER_TEMPERATURE_FALLBACK", "0").lower() in ("1", "true", "yes", "on")
# A transcription whose average log-probability is below this, or whose no-speech
# probability is above WHISPER_LOW_NO_SPEECH, is logged as low confidence.
WHISPER_LOW_LOGPROB = float(os.getenv("WHISPER_LOW_LOGPROB", "-1.0"))
WHISPER_LOW_NO_SPEECH = float(os.getenv("WHISPER_LOW_NO_SPEECH", "0.6"))
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