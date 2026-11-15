from ultron.config import BARGE_IN, END_SILENCE_SECONDS, SLEEP_WORD, WAKE_PHRASE
from ultron.audio.bargein import BargeInDetector
import sys
import time
from ultron.audio.capture import audio_handler, check_keyboard_hit, clear_keyboard_hit
from ultron.audio.wakeword import WakeWordDetector
from ultron.brain import brain
from ultron import activity
from ultron import memory
from ultron.commands import intent
from ultron.commands import context
from ultron.commands.router import NO_WORDS, YES_WORDS, Interaction, repair, route, run_tool_call, tool_schemas
from ultron.commands.text import is_noise
from ultron.commands.text import normalize, is_stop_phrase
from ultron.commands.followups import resolve as resolve_followup
from ultron.voice.speaker import speak, stop_speaking, wait_speaking, is_speaking, prewarm, first_sound_at
from ultron.logger import logger
from ultron.hardware import get_profile
from ultron.stt.whisper import SpeechToText
from ultron import persona

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


class VoiceInteraction(Interaction):
    """How commands talk back by voice: the spoken confirm, "Did you mean?", announcements."""

    def __init__(self, whisper_model, detector):
        self.whisper_model, self.detector = whisper_model, detector

    def confirm(self, prompt: str) -> bool:
        return ask_confirmation(prompt, self.whisper_model)

    def ask_yes_no(self, prompt: str) -> bool | str:
        """Yes, no (or silence), or the words themselves when the answer is a new request."""
        speak(prompt)
        wait_speaking()
        reply = transcribe(self.whisper_model, audio_handler.record_phrase(max_seconds=CONFIRM_LISTEN_SECONDS))
        n = normalize(reply)
        if n in YES_WORDS:
            answer = True
        elif not n or n in NO_WORDS or is_noise(reply):
            answer = False
        else:
            answer = reply  # a command or a correction: routed as a new sentence
        logger.info(f"Did-you-mean reply: {reply!r} -> {'yes' if answer is True else 'cancelled' if answer is False else 'new request'}")
        return answer

    def announce(self, text: str) -> bool:
        """Say what is about to happen; talking over it cancels the action."""
        interrupted = speak_and_interruptible(text, self.detector)
        if interrupted:
            logger.info(f"Announced action cancelled by the user: {text!r}")
        return interrupted


def note_command(said: str, reply: str, command: str | None = None, args: dict | None = None):
    memory.conversation.note_command(said, reply)
    context.note_run(command, args, said, reply)  # so "not base, best" and "it isn't open" can refer to it
    if log := activity.get_log():
        log.log_command(said, reply)


def answer_with_ai(transcription: str, candidates: list[str], io: VoiceInteraction, detector,
                   timing: dict, scores: dict | None = None, sentence: str | None = None) -> bool:
    """Stream the LLM answer into the speaker; returns True if interrupted.

    The commands the matcher found closest are offered as tools (D30). A valid
    tool call runs through the router with the usual safety rules and its real
    result is spoken; an invalid one is ignored and the question is answered in words.
    """
    first = [True]

    def on_sentence(sentence: str):
        speak(sentence, append=not first[0])
        first[0] = False

    tools = tool_schemas(candidates)
    reply = brain.ask_stream(transcription, on_sentence, tools=tools)
    reply.wait_until_decided()
    timing["llm_first_token"] = reply.first_token_s
    if reply.tool_call is not None:
        reply.join()
        name, arguments = reply.tool_call
        outcome = run_tool_call(name, arguments, candidates, io, scores=scores, sentence=sentence)
        if outcome is not None and outcome.route == "reroute":  # the did-you-mean answer was a new request
            new = route(outcome.sentence, io)
            if new.reply is None:
                return answer_with_ai(outcome.sentence, new.candidates, io, detector, timing, new.scores, new.sentence)
            logger.info(f"Command {new.command} ({new.route}, {new.args}) said: {new.reply!r}")
            note_command(outcome.sentence, new.reply, new.command, new.args)
            return bool(new.reply) and speak_and_interruptible(persona.maybe_quip(new.reply), detector)
        if outcome is not None:
            logger.info(f"Command {outcome.command or name} ({outcome.route}, {outcome.args}) said: {outcome.reply!r}")
            timing["route"], timing["cmd"] = outcome.route, outcome.command or name
            if outcome.command:
                note_command(transcription, outcome.reply or "(done)", outcome.command, outcome.args)
            if not outcome.reply:
                return False
            return speak_and_interruptible(persona.maybe_quip(outcome.reply), detector)
        logger.info(f"Ignored tool call {name}({arguments}) for {transcription!r} (not offered or invalid)")
        return answer_with_ai(transcription, [], io, detector, timing, scores, sentence)  # answer in words instead
    if reply.error and not reply.text:
        return speak_and_interruptible(
            "I am having trouble reaching my local model. Check that Ollama is running.", detector)
    timing["route"] = "llm"
    return speak_and_interruptible(None, detector, stream=reply)
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
            echo = barge.echo_level()
            logger.info(f"barge-in: measured echo {echo:.0f} (x{barge.factor:g} = {echo * barge.factor:.0f}), "
                        f"floor {barge.min_rms:.0f}, trigger above {barge.threshold():.0f}")
        audio_handler.stop_stream()
        
    return interrupted

def main():
    from ultron.commands import apps as _apps
    _apps.warm()  # build the installed-app index now, not on the first "open <app>"
    if sys.prefix == sys.base_prefix:
        logger.warning(
            "Not running inside the project's venv, so libraries or model files may be missing. "
            r"Start ULTRON with: run_ultron.bat"
        )
    print("=" * 50)
    print("                ULTRON INITIALIZATION                ")
    print("=" * 50)
    
    # Play startup tone
    try:
        from ultron.audio.sounds import play_startup_sound
        play_startup_sound()
    except Exception:
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

    io = VoiceInteraction(whisper_model, detector)

    greeting_text = get_startup_greeting()
    logger.info(f"ULTRON startup greeting: {greeting_text}")
    speak(greeting_text)
    wait_speaking()

    from ultron.brain import ask_once

    def summarise(prompt: str) -> str:
        text = ask_once(prompt)
        brain.warm()  # a summary pushes ULTRON's own prompt out of the LLM cache; put it back
        return text

    activity.start_background(summarise)
    import threading
    threading.Thread(target=brain.warm, daemon=True, name="llm-warm").start()  # no cold first answer
    threading.Thread(target=intent.get_matcher, daemon=True, name="matcher-load").start()  # 30 MB, about 1 s
    from ultron.commands import apps
    threading.Thread(target=apps.start_menu_index, daemon=True, name="app-index").start()  # about 1.2 s

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
            if not transcription or is_noise(transcription):
                logger.info(f"No speech recognized{f' (noise {transcription!r} ignored)' if transcription else ''}")
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
                    from ultron.audio.sounds import play_sleep_sound
                    play_sleep_sound()
                except Exception:
                    pass
                break
                
            # Check if this is a direct system command
            # "close it", "louder", "again": follow-ups to the previous command
            followup = resolve_followup(transcription, memory.conversation.last_command)
            if followup:
                logger.info(f"Follow-up {transcription!r} -> {followup!r}")
            # Stages a (rules) and b (meaning matcher); stage c is the LLM's tool call (D30)
            outcome = repair(transcription, io)
            if outcome is not None and outcome.route == "reroute":
                outcome = route(outcome.sentence, io)
            elif outcome is None:
                outcome = route(followup or transcription, io)
            timing.update(outcome.timings)  # rule_ms, match_ms
            timing["route"] = outcome.route
            if outcome.command:
                timing["cmd"] = outcome.command

            if outcome.reply is not None:
                logger.info(f"Command {outcome.command} ({outcome.route}, {outcome.args}) said: {outcome.reply!r}")
                note_command(followup or transcription, outcome.reply, outcome.command, outcome.args)
                if outcome.reply == "":
                    interrupted = False
                else:
                    interrupted = speak_and_interruptible(persona.maybe_quip(outcome.reply), detector)
            else:
                # Ask the LLM, offering the closest commands as tools, streaming its answer into the voice
                interrupted = answer_with_ai(transcription, outcome.candidates, io, detector, timing,
                                             outcome.scores, outcome.sentence)

            heard_at = first_sound_at()
            if heard_at is not None and heard_at >= speech_end:
                timing["first_sound"] = heard_at - speech_end
                timing["after_you_stopped"] = heard_at - speech_end + END_SILENCE_SECONDS
            log_timing(timing)

            if interrupted:
                logger.info("Speech interrupted by user")
                continue

def run():
    """Start ULTRON and keep it running until Ctrl+C."""
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. ULTRON going offline.")
        stop_speaking()
        speak(persona.pick(persona.GOODBYES))
        wait_speaking()
        audio_handler.terminate()
        sys.exit(0)
