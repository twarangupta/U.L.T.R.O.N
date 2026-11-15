"""Stage b: the meaning matcher (D30).

model2vec potion-base-8M turns a sentence into a meaning vector (about 0.1 ms
on the laptop CPU). Every command's examples are embedded once at startup;
a new sentence is compared with all of them by cosine similarity.

A "not a command" set (chat, questions, near misses) and each command's own
not_examples act as a null class: when a sentence is about as close to them
as to the best command, it is not a command.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import numpy as np

from commands.registry import commands

MODEL_ID = "minishlab/potion-base-8M"
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "potion-base-8M")
MODEL_SIZE_MB = 30

# Sentences that are not commands: questions, chat, requests ULTRON cannot do.
NOT_COMMANDS = [
    "how are you", "who are you", "what can you do", "tell me about yourself", "thank you", "thanks a lot",
    "good job", "you are funny", "i like you", "hello", "hi there", "good night", "what is your name",
    "why is the sky blue", "what is the capital of france", "how do vaccines work", "explain quantum physics",
    "what should i eat for dinner", "give me some advice on sleep", "how many calories are in a banana",
    "which laptop should i buy", "what is the best phone under 20000", "recommend a good book",
    "is coffee bad for you", "how do i learn python", "what does api mean", "write me a poem",
    "what's your favourite movie", "do you have feelings", "are you smarter than me",
    "i meant something else", "no that is not what i said", "i was talking about food",
    "what do you think about that", "never mind that question", "can you hear me",
    "make me a cup of tea", "order a pizza", "book a cab", "call my mother", "send a whatsapp message",
    "check my email", "read my messages", "what is the price of gold today", "who won the match yesterday",
    "restart the backend service", "reboot the wifi router", "shut the window, it is cold",
    "open the window in my room", "turn on the lights", "lock the front door", "play cricket with me",
    "what time does the shop close", "how much time do i have left", "remind me to drink water at five",
    "what is my dog's name",
]


def model_available() -> bool:
    return os.path.exists(os.path.join(MODEL_DIR, "model.safetensors"))


def download_model(log=print) -> str:
    """Fetch the model once (D25: say what, why and how big; tqdm shows live progress)."""
    if model_available():
        return MODEL_DIR
    log(f"Downloading the meaning-matcher model {MODEL_ID} (about {MODEL_SIZE_MB} MB, one time). "
        "It lets ULTRON understand new phrasings of commands without the LLM.")
    from huggingface_hub import snapshot_download
    snapshot_download(MODEL_ID, local_dir=MODEL_DIR,
                      allow_patterns=["*.json", "model.safetensors", "*.txt", "*.md"])
    return MODEL_DIR


@dataclass
class Ranked:
    command: str
    score: float      # best similarity to the command's examples
    blocked: float    # best similarity to "not a command" sentences for it

    @property
    def margin(self) -> float:
        return self.score - self.blocked


class Matcher:
    def __init__(self, model=None):
        if model is None:
            from model2vec import StaticModel
            model = StaticModel.from_pretrained(download_model())
        self.model = model
        started = time.perf_counter()
        self._build()
        self.build_seconds = time.perf_counter() - started

    def _embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.asarray(self.model.encode(texts), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-9)

    def _build(self):
        from commands.router import clean
        self.names: list[str] = []
        texts, owners = [], []
        not_texts, not_owners = [clean(t) for t in NOT_COMMANDS], [None] * len(NOT_COMMANDS)
        for cmd in commands("match"):
            self.names.append(cmd.name)
            for ex in cmd.examples:
                texts.append(clean(ex))
                owners.append(cmd.name)
            for ex in cmd.not_examples:
                not_texts.append(clean(ex))
                not_owners.append(cmd.name)
        self._ex = self._embed(texts)
        self._ex_owner = np.array(owners)
        self._not = self._embed(not_texts)
        self._not_owner = np.array([o or "" for o in not_owners])

    def rank(self, text: str) -> list[Ranked]:
        """Commands by similarity, best first (text should already be clean())."""
        if not text.strip():
            return []
        v = self._embed([text])[0]
        sims = self._ex @ v
        not_sims = self._not @ v
        general_block = float(not_sims[self._not_owner == ""].max()) if len(not_sims) else 0.0
        ranked = []
        for name in self.names:
            score = float(sims[self._ex_owner == name].max())
            own = not_sims[self._not_owner == name]
            blocked = max(general_block, float(own.max()) if len(own) else 0.0)
            ranked.append(Ranked(name, score, blocked))
        ranked.sort(key=lambda r: -r.score)
        return ranked


_matcher: Matcher | None = None
_lock = threading.Lock()


def get_matcher(load: bool = True) -> Matcher | None:
    """The shared matcher; None if the model is not on disk and load=False, or loading failed."""
    global _matcher
    if _matcher is None and (load or model_available()):
        with _lock:
            if _matcher is None:
                try:
                    _matcher = Matcher()
                except Exception as e:  # missing package or file: stages a and c still work
                    from logger import logger
                    logger.warning(f"Meaning matcher unavailable: {e}")
                    return None
    return _matcher


def reset():
    """Rebuild on next use (tests that add commands)."""
    global _matcher
    _matcher = None
