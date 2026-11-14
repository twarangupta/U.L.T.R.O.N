from datetime import datetime

import ollama
from config import OLLAMA_SYSTEM_PROMPT
from hardware import get_profile
from logger import logger

class Brain:
    """
    Manages the offline conversation brain powered by Ollama.
    Maintains dialogue history to support continuous conversational context.
    """
    def __init__(self):
        self.model = get_profile().llm_model
        self.system_prompt = OLLAMA_SYSTEM_PROMPT
        self.history = []
        self.reset_conversation()
        self.verify_ollama_model()

    def verify_ollama_model(self) -> bool:
        """Checks connection to Ollama and verifies if the configured model is pulled."""
        try:
            models_list = ollama.list()
            available_models = [m.get("model") for m in models_list.get("models", [])]
            # Ollama model names might include tags, e.g. 'llama3.2:3b' or 'llama3.2:latest'
            match_found = False
            for model_info in models_list.get("models", []):
                name = model_info.get("model", "")
                if self.model in name or name in self.model:
                    match_found = True
                    break
            
            if not match_found:
                logger.warning(
                    f"Model '{self.model}' was not detected in local Ollama repository. "
                    f"Please run 'ollama pull {self.model}' if queries fail."
                )
            else:
                logger.info(f"Ollama model '{self.model}' verified successfully.")
            return True
        except Exception as e:
            logger.error(
                f"Ollama server is not running or unreachable. Please launch Ollama. Error: {e}"
            )
            return False

    def reset_conversation(self):
        """Resets conversational memory and injects the system prompt."""
        self.history = [
            {"role": "system", "content": self.system_prompt}
        ]

    def ask(self, question: str) -> str:
        """
        Sends the question along with context history to the local Ollama instance
        and returns the AI's spoken response.
        """
        self.history.append({"role": "user", "content": question})
        try:
            # The model has no clock. Give it the real time on every call (not
            # stored in history) so it never invents one.
            system = f"{self.system_prompt}\n\n{current_time_note()}"
            messages = [{"role": "system", "content": system}] + self.history[1:]
            response = ollama.chat(
                model=self.model,
                messages=messages
            )
            reply = response.get("message", {}).get("content", "")
            if not reply:
                reply = "I apologize, but I received empty telemetry from my brain core."
            
            self.history.append({"role": "assistant", "content": reply})
            return reply
            
        except Exception as e:
            error_msg = f"Brain communication error: {e}"
            logger.error(error_msg)
            # Do not append error message to history to keep it clean
            return "I am having trouble accessing my local cognitive models. Please verify Ollama is active."

def current_time_note() -> str:
    from commands.clock import spoken_date, spoken_time
    now = datetime.now().astimezone()
    return (
        f"Current local date and time: {spoken_date(now)}, {spoken_time(now)} ({now.tzname()}). "
        "Use this for any question about the time, date or day. Never guess a time."
    )


# Singleton instance
brain = Brain()

def ask_ai(question: str) -> str:
    """Convenience helper to ask the brain."""
    return brain.ask(question)

def reset_brain():
    """Convenience helper to clear memory."""
    brain.reset_conversation()