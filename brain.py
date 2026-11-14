from datetime import datetime

import ollama

import activity
import memory
from config import OLLAMA_SYSTEM_PROMPT
from hardware import get_profile
from logger import logger

class Brain:
    """
    Manages the offline conversation brain powered by Ollama.
    The conversation and long-term facts live in memory.py.
    """
    def __init__(self):
        self.model = get_profile().llm_model
        self.system_prompt = OLLAMA_SYSTEM_PROMPT
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
        """Forget the conversation (long-term facts stay)."""
        memory.conversation.clear()

    def build_messages(self, question: str) -> list[dict]:
        """System prompt, the real time, saved facts, the recent exchanges, the question.

        The model has no clock, so it gets the time on every call (never stored).
        """
        parts = (self.system_prompt, current_time_note(), memory.facts.prompt_note(),
                 activity.prompt_note(activity.get_log()))
        system = "\n\n".join(part for part in parts if part)
        return ([{"role": "system", "content": system}] + memory.conversation.recent()
                + [{"role": "user", "content": question}])

    def ask(self, question: str) -> str:
        """Ask the local LLM and return its spoken reply. The exchange is remembered."""
        try:
            response = ollama.chat(model=self.model, messages=self.build_messages(question))
            reply = response.get("message", {}).get("content", "")
            if not reply:
                reply = "I apologize, but I received empty telemetry from my brain core."
            memory.conversation.add_exchange(question, reply)
            return reply
        except Exception as e:
            logger.error(f"Brain communication error: {e}")
            # Errors are not remembered, to keep the history clean.
            return "I am having trouble accessing my local cognitive models. Please verify Ollama is active."


def ask_once(prompt: str) -> str:
    """One standalone question (no persona, no conversation), e.g. for summaries."""
    try:
        response = ollama.chat(model=brain.model, messages=[{"role": "user", "content": prompt}],
                               options={"num_predict": 200})
        return response.get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.debug(f"ask_once failed: {e}")
        return ""


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
    """Forget the conversation (long-term facts stay)."""
    brain.reset_conversation()