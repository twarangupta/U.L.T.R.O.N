from config import BARGE_IN, END_SILENCE_SECONDS, SLEEP_WORD, WAKE_PHRASE
from bargein import BargeInDetector
import re
import sys
import time
from audio import audio_handler, check_keyboard_hit, clear_keyboard_hit
from wakeword import WakeWordDetector
from brain import brain
import activity
import memory
from commands import execute_command
from commands.text import normalize, is_stop_phrase
from commands.ai_routing import allowed_ai_command
from commands.followups import resolve as resolve_followup
from speaker import speak, stop_speaking, wait_speaking, is_speaking, prewarm, first_sound_at
from logger import logger
from hardware import get_profile
from stt import SpeechToText
import persona

def get_startup_greeting() -> str:
    import random
    import urllib.request
    import json
    import psutil

    candidates = [persona.pick(persona.GREETINGS)]

    # Weather by IP location (max 1.5 s per request)
    try:
        req = urllib.request.Request("http://ip-api.com/json/", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=1.5) as response:
            data = json.loads(response.read().decode())
        city, lat, lon = data.get("city"), data.get("lat"), data.get("lon")
        if city and lat is not None and lon is not None:
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            req2 = urllib.request.Request(weather_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req2, timeout=1.5) as response:
                temp = json.loads(response.read().decode()).get("current_weather", {}).get("temperature")
            if temp is not None:
                candidates.append(persona.pick(persona.WEATHER_GREETINGS, temp=temp, city=city))
    except Exception:
        pass

    # Battery
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            status = "plugged in" if battery.power_plugged else "on battery"
            candidates.append(persona.pick(persona.BATTERY_GREETINGS, percent=battery.percent, status=status))
    except Exception:
        pass

    return random.choice(candidates)

# Replies that approve a risky command. Anything else cancels it.
CONFIRM_WORDS = {"confirm", "confirmed", "yes confirm", "i confirm"}
CONFIRM_LISTEN_SECONDS = 6.0


def transcribe(whisper_model, audio_data) -> str:
    """Speech to text. Returns "" on silence or error."""
    return whisper_model.transcribe(audio_data)


def ask_confirmation(prompt: str, whisper_model) -> bool:
    """Speak the prompt, listen once, and return True only for "confirm"."""
    speak(prompt)
    wait_speaking()
    reply = transcribe(whisper_model, audio_handler.record_phrase(max_seconds=CONFIRM_LISTEN_SECONDS))
    approved = normalize(reply) in CONFIRM_WORDS
    logger.info(f"Confirmation reply: {reply!r} -> {'approved' if approved else 'cancelled'}")
    return approved


def is_sleep_phrase(transcription: str) -> bool:
    """True only when the whole utterance is the sleep phrase.

    "Go to sleep." sleeps; "remind me to go to sleep at 11" does not.
    """
    return normalize(transcription) == normalize(SLEEP_WORD)


COMMAND_TAG = re.compile(r"COMMAND:\s*([a-zA-Z0-9_\-\s]+)", re.IGNORECASE)
COMMAND_BLOCK = re.compile(r"[`\[]*[^`\[]*COMMAND:\s*[^\]`]+[\]`]*", re.IGNORECASE)


def handle_ai_reply(transcription: str, ai_response: str, confirm) -> str:
    """Run a command the LLM asked for, if it is allowed, and return what to say.

    When a command runs, ULTRON speaks the command's real result, not the
    model's text (which may claim something that did not happen).
    """
    logger.info(f"AI reply: {ai_response!r}")
    match = COMMAND_TAG.search(ai_response)
    if not match:
        return ai_response
    command = match.group(1).strip()
    natural_reply = COMMAND_BLOCK.sub("", ai_response).strip()

    if not allowed_ai_command(transcription, command):
        logger.info(f"Ignored AI command {command!r} for {transcription!r} (not allowed)")
        return persona.pick(persona.UNSURE_REPLIES)

    logger.info(f"AI command routed: {command!r}")
    result = execute_command(command, confirm)
    if result:
        return result
    return natural_reply or persona.pick(persona.DONE_REPLIES)


def answer_with_ai(transcription: str, confirm, detector, timing: dict) -> bool:
    """Stream the LLM answer into the speaker; returns True if interrupted.

    The first sentence starts playing while the rest is still being written.
    A [COMMAND: x] reply is not streamed: it is run (if allowed) and its real
    result is spoken.
    """
    first = [True]

    def on_sentence(sentence: str):
        speak(sentence, append=not first[0])
        first[0] = False

    reply = brain.ask_stream(transcription, on_sentence)
    reply.wait_until_decided()
    if reply.is_command:
        reply.join()
        spoken = handle_ai_reply(transcription, reply.text, confirm)
        memory.conversation.replace_last_reply(spoken)  # remember what really happened
        interrupted = speak_and_interruptible(spoken, detector)
    elif reply.error and not reply.text:
        interrupted = speak_and_interruptible(
            "I am having trouble reaching my local model. Check that Ollama is running.", detector)
    else:
        interrupted = speak_and_interruptible(None, detector, stream=reply)
    timing["llm_first_token"] = reply.first_token_s
    return interrupted


def log_timing(timing: dict):
    """One line per request: where the time went, measured from the end of speech."""
    parts = [f"{key}={value:.2f}" for key, value in timing.items() if isinstance(value, float)]
    parts += [f"{key}={value}" for key, value in timing.items() if isinstance(value, str)]
    logger.info("timing: " + " ".join(parts))


# Audio captured when the user talked over ULTRON; the next recording starts with it.
pending_preroll: list = []


def speak_and_interruptible(text: str | None, detector: WakeWordDetector, stream=None) -> bool:
    """
    Plays the response. While speaking, continuously streams mic audio and checks for the wake word.
    If the wake word is detected, stops speaking immediately and returns True.
    With a stream (a StreamingReply), text is None: its sentences are already
    being queued, and listening lasts until the stream ends and speech stops.
    """
    # Reset prediction buffers to clear the wake-up word trigger
    detector.reset()

    if text is not None:
        speak(text)
    
    # Start microphone stream to monitor for interrupt wake word
    audio_handler.start_stream()

    interrupted = False
    chunks_count = 0
    barge = BargeInDetector() if BARGE_IN else None
    try:
        while is_speaking() or (stream is not None and stream.alive()):
            # Keyboard interruption fallback
            if check_keyboard_hit():
                clear_keyboard_hit()
                if stream is not None:
                    stream.cancel()
                stop_speaking()
                interrupted = True
                logger.info("Speech interrupted by keyboard")
                break
                
            chunk = audio_handler.read_chunk()
            chunks_count += 1
            
            # Check for wake word but ignore the first ~0.5 seconds (6 chunks)
            # of audio to prevent triggering from the trailing wake-up audio.
            if detector.is_wake_word(chunk):
                if chunks_count > 6:
                    if stream is not None:
                        stream.cancel()
                    stop_speaking()
                    interrupted = True
                    break

            # Talking over ULTRON stops it; what you said starts the next recording.
            if barge is not None and barge.feed(chunk):
                if stream is not None:
                    stream.cancel()
                stop_speaking()
                interrupted = True
                pending_preroll[:] = barge.preroll()
                logger.info("Speech interrupted by voice")
                break
    finally:
        if barge is not None and barge.seen > 6:
            logger.info(f"barge-in: echo level {barge.threshold() / barge.factor:.0f}, "
                        f"trigger above {barge.threshold():.0f}")
        audio_handler.stop_stream()
        
    return interrupted

def main():
    if sys.prefix == sys.base_prefix:
        logger.warning(
            "Not running inside the project's venv, so libraries or model files may be missing. "
            r"Start ULTRON with: venv\Scripts\python.exe ultron.py"
        )
    print("=" * 50)
    print("                ULTRON INITIALIZATION                ")
    print("=" * 50)
    
    # Play startup tone
    try:
        from startup_audio import play_startup_sound
        play_startup_sound()
    except:
        pass
    
    # 1. Initialize text-to-speech speaker
    speak("Initializing system protocols.")
    prewarm(persona.fixed_lines())  # instant playback for fixed lines
    wait_speaking()

    # 2. Initialize Wake Word Detector
    try:
        detector = WakeWordDetector()
    except Exception as e:
        logger.error(f"Failed to initialize Wake Word Detector: {e}")
        speak("Error loading wake word engine. Exiting.")
        wait_speaking()
        sys.exit(1)

    # 3. Initialize Faster-Whisper
    speak("Loading speech recognition models.")
    wait_speaking()
    try:
        whisper_model = SpeechToText(get_profile())
    except Exception as e:
        logger.error(f"Failed to initialize Whisper model: {e}")
        speak("Error loading speech recognition model. Exiting.")
        wait_speaking()
        sys.exit(1)

    def confirm(prompt: str) -> bool:
        return ask_confirmation(prompt, whisper_model)

    greeting_text = get_startup_greeting()
    logger.info(f"ULTRON startup greeting: {greeting_text}")
    speak(greeting_text)
    wait_speaking()

    from brain import ask_once

    def summarise(prompt: str) -> str:
        text = ask_once(prompt)
        brain.warm()  # a summary pushes ULTRON's own prompt out of the LLM cache; put it back
        return text

    activity.start_background(summarise)
    import threading
    threading.Thread(target=brain.warm, daemon=True, name="llm-warm").start()  # no cold first answer

    # Main infinite loop
    while True:
        if log := activity.get_log():
            log.busy = False
            log.last_used = time.monotonic()
        logger.info(f"Status: Sleeping. Standing by. Say \"{WAKE_PHRASE}\" to wake me...")
        
        # Start continuous audio stream for wake word monitoring
        if not audio_handler.start_stream():
            logger.error("Microphone hardware connection is missing or blocked. Retrying in 5 seconds...")
            time.sleep(5)
            continue
        
        while True:
            # Read streaming audio chunk
            chunk = audio_handler.read_chunk()
            
            # Check for wake word
            if detector.is_wake_word(chunk):
                break
                
        # Stop wake-word streaming to switch mode
        audio_handler.stop_stream()
        # The conversation survives naps; only a long silence wipes it.
        memory.conversation.expire_if_idle()
        if log := activity.get_log():
            log.busy = True  # no summaries while we talk
        
        # Greeting (interruptible)
        interrupted = speak_and_interruptible(persona.pick(persona.WAKE_REPLIES), detector)
        
        # Conversation loop
        while True:
            if interrupted:
                interrupted = False
                
            # Record user phrase with silence detection
            preroll, pending_preroll[:] = list(pending_preroll), []
            audio_data = audio_handler.record_phrase(silence_timeout_seconds=END_SILENCE_SECONDS, preroll=preroll)
            speech_end = time.perf_counter()  # END_SILENCE_SECONDS after you actually stopped
            timing = {"end_wait": END_SILENCE_SECONDS}

            logger.info("Transcribing...")
            transcription = transcribe(whisper_model, audio_data)
            timing["stt"] = time.perf_counter() - speech_end
            if not transcription:
                logger.info("No speech recognized")
                continue
                
            print(f"You: {transcription}")
            logger.info(f"Heard: {transcription!r}")
            
            # "Stop", "cancel", "never mind": stand down and go back to sleep
            if is_stop_phrase(transcription):
                logger.info("Stop phrase heard. Going back to sleep.")
                speak(persona.pick(persona.STOP_REPLIES))
                wait_speaking()
                break

            # Sleep only when the whole utterance is the sleep phrase
            if is_sleep_phrase(transcription):
                speak(persona.pick(persona.SLEEP_REPLIES))
                wait_speaking()
                try:
                    from startup_audio import play_sleep_sound
                    play_sleep_sound()
                except:
                    pass
                break
                
            # Check if this is a direct system command
            # "close it", "louder", "again": follow-ups to the previous command
            followup = resolve_followup(transcription, memory.conversation.last_command)
            if followup:
                logger.info(f"Follow-up {transcription!r} -> {followup!r}")
            command_response = execute_command(followup or transcription, confirm)
            
            if command_response is not None:
                memory.conversation.note_command(followup or transcription, command_response)
                if log := activity.get_log():
                    log.log_command(followup or transcription, command_response)
                if command_response == "":
                    interrupted = False
                else:
                    interrupted = speak_and_interruptible(persona.maybe_quip(command_response), detector)
            else:
                # Ask the LLM, streaming its answer into the voice
                interrupted = answer_with_ai(transcription, confirm, detector, timing)

            timing["route"] = "command" if command_response is not None else "llm"
            heard_at = first_sound_at()
            if heard_at is not None and heard_at >= speech_end:
                timing["first_sound"] = heard_at - speech_end
                timing["after_you_stopped"] = heard_at - speech_end + END_SILENCE_SECONDS
            log_timing(timing)

            if interrupted:
                logger.info("Speech interrupted by user")
                continue

if __name__ == "__main__":
    if "--benchmark" in sys.argv:
        from benchmark import run_benchmark
        sys.exit(run_benchmark())
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. ULTRON going offline.")
        stop_speaking()
        speak(persona.pick(persona.GOODBYES))
        wait_speaking()
        audio_handler.terminate()
        sys.exit(0)