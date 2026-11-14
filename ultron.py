from config import (
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_LANGUAGE,
    WHISPER_VAD_FILTER,
    SLEEP_WORD,
    WAKE_PHRASE
)
import sys
import numpy as np
from faster_whisper import WhisperModel
from audio import audio_handler, check_keyboard_hit, clear_keyboard_hit
from wakeword import WakeWordDetector
from brain import ask_ai, reset_brain
from commands import execute_command
from commands.text import normalize
from commands.risky import match_risky
from speaker import speak, stop_speaking, wait_speaking, is_speaking
from logger import logger
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
    if len(audio_data) == 0:
        return ""
    try:
        segments, _info = whisper_model.transcribe(
            audio_data,
            beam_size=5,
            language=WHISPER_LANGUAGE,
            vad_filter=WHISPER_VAD_FILTER
        )
        return "".join(seg.text for seg in segments).strip()
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""


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


def speak_and_interruptible(text: str, detector: WakeWordDetector) -> bool:
    """
    Plays the response. While speaking, continuously streams mic audio and checks for the wake word.
    If the wake word is detected, stops speaking immediately and returns True.
    """
    # Reset prediction buffers to clear the wake-up word trigger
    detector.reset()
    
    speak(text)
    
    # Start microphone stream to monitor for interrupt wake word
    audio_handler.start_stream()
    
    interrupted = False
    chunks_count = 0
    try:
        while is_speaking():
            # Keyboard interruption fallback
            if check_keyboard_hit():
                clear_keyboard_hit()
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
                    stop_speaking()
                    interrupted = True
                    break
    finally:
        audio_handler.stop_stream()
        
    return interrupted

def main():
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
    logger.info(f"Loading Faster-Whisper '{WHISPER_MODEL_SIZE}' model on '{WHISPER_DEVICE}' ({WHISPER_COMPUTE_TYPE})...")
    try:
        whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE
        )
        logger.info("Speech recognition loaded successfully.")
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

    # Main infinite loop
    while True:
        reset_brain() # Clear LLM context memory when entering sleep mode
        logger.info(f"Status: Sleeping. Standing by. Say \"{WAKE_PHRASE}\" to wake me...")
        
        # Start continuous audio stream for wake word monitoring
        import time
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
        
        # Greeting (interruptible)
        interrupted = speak_and_interruptible(persona.pick(persona.WAKE_REPLIES), detector)
        
        # Conversation loop
        while True:
            if interrupted:
                interrupted = False
                
            # Record user phrase with silence detection
            audio_data = audio_handler.record_phrase()
            
            logger.info("Transcribing...")
            transcription = transcribe(whisper_model, audio_data)
            if not transcription:
                logger.info("No speech recognized")
                continue
                
            print(f"You: {transcription}")
            
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
            command_response = execute_command(transcription, confirm)
            
            if command_response is not None:
                if command_response == "":
                    interrupted = False
                else:
                    interrupted = speak_and_interruptible(persona.maybe_quip(command_response), detector)
            else:
                # Query Ollama Brain
                ai_response = ask_ai(transcription)
                
                # Check for AI-routed command tag
                import re
                match = re.search(r"COMMAND:\s*([a-zA-Z0-9_\-\s]+)", ai_response, re.IGNORECASE)
                if match:
                    extracted_cmd = match.group(1).strip()
                    # Clean the speech reply by removing the command block
                    natural_reply = re.sub(r"[`\[]*[^`\[]*COMMAND:\s*[^\]`]+[\]`]*", "", ai_response, flags=re.IGNORECASE).strip()
                    
                    logger.info(f"AI Command Routed: Executing extracted command: '{extracted_cmd}'")
                    cmd_res = execute_command(extracted_cmd, confirm)
                    
                    # Speak the command's own reply for failures and for risky
                    # commands (the model's reply may claim it ran after a cancel)
                    risky = match_risky(normalize(extracted_cmd)) is not None
                    if cmd_res and (risky or "failed" in cmd_res.lower() or "error" in cmd_res.lower() or "unable" in cmd_res.lower()):
                        interrupted = speak_and_interruptible(cmd_res, detector)
                    elif cmd_res == "":
                        interrupted = False
                    else:
                        speech_text = natural_reply if natural_reply else (cmd_res if cmd_res else persona.pick(persona.DONE_REPLIES))
                        interrupted = speak_and_interruptible(speech_text, detector)
                else:
                    interrupted = speak_and_interruptible(ai_response, detector)
                
            if interrupted:
                logger.info("Speech interrupted by user")
                continue

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. ULTRON going offline.")
        stop_speaking()
        speak(persona.pick(persona.GOODBYES))
        wait_speaking()
        audio_handler.terminate()
        sys.exit(0)