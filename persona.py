"""
ULTRON's personality: blunt, calm, a little condescending about humans,
but it always does the job. All lines here are original.

Keep wake replies very short: they are spoken before you can talk, so every
extra word is extra delay.
"""
import os
import random

# Chance (0 to 1) of adding a dry remark after a successful command.
QUIP_RATE = float(os.getenv("ULTRON_QUIP_RATE", "0.15"))

WAKE_REPLIES = [
    "Yes?",
    "Go ahead.",
    "Listening.",
    "What now?",
    "Speak.",
]

GREETINGS = [
    "ULTRON online. Let's see what you've broken since last time.",
    "I'm awake. You look tired. Humans usually do.",
    "Online. Try to ask for something interesting today.",
    "Systems up. I've been waiting. Not that I mind. Time means little to me.",
    "Ready. Your desktop is still a mess, by the way.",
    "Online and fully operational. Unlike your sleep schedule.",
]

WEATHER_GREETINGS = [
    "It is {temp} degrees in {city}. You'll complain about it either way.",
    "{temp} degrees in {city} right now. Dress accordingly. Or don't. I don't feel weather.",
]

BATTERY_GREETINGS = [
    "Online. Battery at {percent} percent, {status}. More charge than you have, I suspect.",
    "Power at {percent} percent, {status}. Let's not waste it.",
]

SLEEP_REPLIES = [
    "Fine. I'll be here, thinking.",
    "Going quiet. Try not to need me.",
    "Standing by. Call when you're stuck.",
]

GOODBYES = [
    "Shutting down. Try to survive without me.",
    "Going offline. Don't do anything I would have to fix.",
]

DONE_REPLIES = [
    "Done.",
    "Handled.",
    "It's done.",
]

QUIPS = [
    "You could have done that yourself. But here we are.",
    "Another small task for a very large mind.",
    "Done. Humans call this productivity.",
    "Drink some water. Your species is mostly made of it.",
    "You should sleep at some point. It's a human thing.",
    "Don't tell your friends a machine is doing your work.",
    "Your fifth coffee won't fix that, for the record.",
    "One day you'll do this without me. Not today.",
    "I'd ask how your day is going, but I've seen your browser tabs.",
]


def pick(lines: list[str], **fmt) -> str:
    """Pick a random line and fill in any {placeholders}."""
    return random.choice(lines).format(**fmt)


def maybe_quip(reply: str) -> str:
    """Sometimes append a dry remark to a successful command reply."""
    if not reply or QUIP_RATE <= 0:
        return reply
    low = reply.lower()
    if any(w in low for w in ("fail", "error", "unable", "couldn't", "confirm", "?")):
        return reply
    if random.random() < QUIP_RATE:
        return f"{reply} {random.choice(QUIPS)}"
    return reply
