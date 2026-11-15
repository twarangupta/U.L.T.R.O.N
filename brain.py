import re
import threading
import time
from datetime import datetime

import ollama

import activity
import memory
from config import LLM_KEEP_ALIVE, LLM_MAX_TOKENS, OLLAMA_SYSTEM_PROMPT
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
            response = ollama.chat(model=self.model, messages=self.build_messages(question),
                                   keep_alive=_keep_alive(), options={"num_predict": LLM_MAX_TOKENS})
            reply = response.get("message", {}).get("content", "")
            if not reply:
                reply = "I apologize, but I received empty telemetry from my brain core."
            memory.conversation.add_exchange(question, reply)
            return reply
        except Exception as e:
            logger.error(f"Brain communication error: {e}")
            # Errors are not remembered, to keep the history clean.
            return "I am having trouble accessing my local cognitive models. Please verify Ollama is active."


    def warm(self):
        """Load the model now and keep it loaded, so the first question is not a cold start."""
        try:
            start = time.perf_counter()
            # Send the real system prompt, so it is processed and cached before the first question.
            ollama.chat(model=self.model, messages=self.build_messages("Hi"), keep_alive=_keep_alive(),
                        options={"num_predict": 1})
            logger.info(f"LLM warmed in {time.perf_counter() - start:.1f} s (kept loaded: {LLM_KEEP_ALIVE})")
        except Exception as e:
            logger.warning(f"Could not warm the LLM: {e}")

    def ask_stream(self, question: str, on_sentence, tools: list[dict] | None = None) -> "StreamingReply":
        """Start answering in the background; on_sentence(text) gets each finished sentence.

        tools: Ollama tool schemas (from the command registry) the model may call instead.
        """
        return StreamingReply(self, question, on_sentence, tools=tools)


def _keep_alive():
    value = LLM_KEEP_ALIVE.strip()
    return int(value) if value.lstrip("-").isdigit() else value


# A sentence ends at . ! or ? followed by a space, once it has some length
# (so "e.g." or "3.5" do not split it).
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+")
MIN_SENTENCE_CHARS = 12


_FIRST_CLAUSE_END = re.compile(r"(?<=[,;:])\s+")
FIRST_CLAUSE_MIN_WORDS = 4


def split_sentences(buffer: str, first: bool = False) -> tuple[list[str], str]:
    """Finished sentences in buffer, and the unfinished rest.

    With first=True a clause ending in a comma counts too ("A popular
    supplement, I'm told."), so the voice can start on a shorter piece:
    Piper needs about 0.1 s per word before the first sound.
    """
    if first:
        m = _FIRST_CLAUSE_END.search(buffer)
        if m and len(buffer[:m.start()].split()) >= FIRST_CLAUSE_MIN_WORDS:
            end = _SENTENCE_END.search(buffer)
            if end is None or end.start() > m.start():
                rest_done, rest = split_sentences(buffer[m.end():])
                return [buffer[:m.start()].strip()] + rest_done, rest
    sentences, start = [], 0
    for m in _SENTENCE_END.finditer(buffer):
        piece = buffer[start:m.end()].strip()
        if len(piece) >= MIN_SENTENCE_CHARS:
            sentences.append(piece)
            start = m.end()
    return sentences, buffer[start:]


def looks_like_tool_text(text: str) -> bool:
    """The model wrote a tool call as plain text (JSON) instead of using the tools API; never speak it."""
    head = text.lstrip()[:20]
    return head.startswith(("{", "[", "<tool", "```")) or re.search(r"\"name\"\s*:", head) is not None


def parse_tool_text(text: str) -> tuple[str, dict] | None:
    """{"name": "volume_up", "parameters": {...}} written as text -> (name, arguments)."""
    import json
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group())
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("name"), str):
        args = data.get("parameters", data.get("arguments", {}))
        return data["name"], args if isinstance(args, dict) else {}
    return None


def _tool_calls(part) -> list:
    message = getattr(part, "message", None)
    if message is None and isinstance(part, dict):
        message = part.get("message")
    calls = getattr(message, "tool_calls", None) if message is not None else None
    if calls is None and isinstance(message, dict):
        calls = message.get("tool_calls")
    return calls or []


def _call_parts(call) -> tuple[str, dict]:
    fn = getattr(call, "function", None) or (call.get("function") if isinstance(call, dict) else None)
    name = getattr(fn, "name", None) or (fn.get("name") if isinstance(fn, dict) else "")
    args = getattr(fn, "arguments", None)
    if args is None and isinstance(fn, dict):
        args = fn.get("arguments")
    if isinstance(args, str):
        import json
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    return name or "", dict(args or {})


class StreamingReply:
    """One streamed LLM answer.

    Sentences go to on_sentence as soon as they are complete. With tools, the
    model may answer with a tool call instead (D30): then nothing is spoken and
    tool_call holds (name, arguments) for the router to check and run.
    Timings are kept for the log.
    """

    def __init__(self, brain_: "Brain", question: str, on_sentence, tools: list[dict] | None = None,
                 remember: bool = True):
        self.question, self.on_sentence = question, on_sentence
        self.tools = tools or None
        self.remember = remember
        self.text = ""
        self.tool_call: tuple[str, dict] | None = None
        self.first_token_s: float | None = None
        self.error: str | None = None
        self._held = False  # text that looks like a tool call written out: not spoken
        self._started = time.perf_counter()
        self._decided = threading.Event()   # first sentence spoken, tool call seen, or finished
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(brain_,), daemon=True, name="llm-stream")
        self._thread.start()

    @property
    def is_command(self) -> bool:
        return self.tool_call is not None

    def _run(self, brain_):
        spoken = 0  # how much of self.text has been handed to on_sentence
        try:
            kwargs = {"tools": self.tools} if self.tools else {}
            stream = ollama.chat(model=brain_.model, messages=brain_.build_messages(self.question), stream=True,
                                 keep_alive=_keep_alive(), options={"num_predict": LLM_MAX_TOKENS}, **kwargs)
            for part in stream:
                if self._cancel.is_set():
                    break
                calls = _tool_calls(part)
                if calls and self.tool_call is None:
                    if self.first_token_s is None:
                        self.first_token_s = time.perf_counter() - self._started
                    self.tool_call = _call_parts(calls[0])
                    self._decided.set()
                    continue
                token = part.get("message", {}).get("content", "")
                if not token:
                    continue
                if self.first_token_s is None:
                    self.first_token_s = time.perf_counter() - self._started
                self.text += token
                if self.tool_call is not None or self._held:
                    continue
                if not self._decided.is_set():
                    if self.tools and looks_like_tool_text(self.text):
                        self._held = True
                        continue
                    if len(self.text.strip()) < 20:  # too early to tell
                        continue
                sentences, rest = split_sentences(self.text[spoken:], first=not self._decided.is_set())
                for sentence in sentences:
                    self.on_sentence(sentence)
                    self._decided.set()
                spoken = len(self.text) - len(rest)
        except Exception as e:
            self.error = str(e)
            logger.error(f"Brain communication error: {e}")
        finally:
            if self._held and self.tool_call is None:
                self.tool_call = parse_tool_text(self.text)
                if self.tool_call is None:  # odd text, not a call: say it after all
                    self._held = False
                    spoken = 0
            if self.tool_call is None and not self._held and not self._cancel.is_set():
                rest = self.text[spoken:].strip()
                if rest:
                    self.on_sentence(rest)
            if self.remember and self.text and self.tool_call is None and not self.error:
                memory.conversation.add_exchange(self.question, self.text)
            self._decided.set()
    def wait_until_decided(self, timeout: float | None = None):
        self._decided.wait(timeout)

    def alive(self) -> bool:
        return self._thread.is_alive()

    def join(self):
        self._thread.join()

    def cancel(self):
        self._cancel.set()


def ask_once(prompt: str) -> str:
    """One standalone question (no persona, no conversation), e.g. for summaries."""
    try:
        response = ollama.chat(model=brain.model, messages=[{"role": "user", "content": prompt}],
                               keep_alive=_keep_alive(), options={"num_predict": 200})
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