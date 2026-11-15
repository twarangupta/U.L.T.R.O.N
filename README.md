# ULTRON

A free, local, hands-free voice assistant that controls your Windows PC. Wake word, speech recognition, a language model and the voice all run on your own machine. Nothing is sent to the cloud. It has a blunt, dry personality: it mocks human habits now and then, but it always does the job.

- Say "Hey Ultron" (until the custom model is trained, "Hey Jarvis" is used), then talk normally. Simple commands answer in well under a second.
- It understands many phrasings of each command, not just fixed sentences (see [How it understands you](#how-it-understands-you)).
- Risky actions (shutdown, restart, empty the recycle bin) always need a spoken "confirm".
- It picks smaller models on small PCs and uses the GPU fully on strong ones.

## Requirements

- Windows 10 or 11, a microphone and speakers.
- Python 3.11.
- [Ollama](https://ollama.com) for the language model.
- 8 GB RAM is enough (5.9 GB laptops work). An NVIDIA GPU is optional and makes it faster.

## Install

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install -e ".[gpu]"
venv\Scripts\python.exe tools\download_voice.py
ollama pull qwen2.5:3b
```

- Leave out `[gpu]` if you have no NVIDIA card (about 550 MB saved; Whisper then runs on the CPU).
- The 30 MB meaning-matcher model downloads by itself on first start.
- Settings are optional and go in a `.env` file in this folder (see `src/ultron/config.py` for every name).

## First run

```bash
run_ultron.bat
```

`run_ultron.bat --self-test` checks the settings, the command list and the hardware profile without touching the microphone or any model. `run_ultron.bat --benchmark` shows which models were chosen for your PC and how fast they are.

Press Ctrl+C to quit; ULTRON says goodbye first.

## Main commands

The full list, generated from the code, is in [docs/COMMANDS.md](docs/COMMANDS.md). A taste:

| You say | What happens |
|---|---|
| "Open Chrome", "close Spotify", "switch to VS Code" | Opens, closes or focuses the app |
| "Volume up", "set volume to 30", "mute" | Controls the sound |
| "Next song", "pause" | Media keys |
| "Git status", "git push", "create branch x" | Git in the current project |
| "What time is it?", "what day is it?" | Reads the PC clock |
| "Remember that my locker code is 4821" | Saves a fact; "what do you remember" lists them |
| "What did I do yesterday?", "continue where I left off" | Uses the activity log |
| "Type hello world" | Types the words where the cursor is |
| "Shut down the computer" | Asks for "confirm" first |
| "Stop" or "go to sleep" | Ends the conversation |

Anything that is not a command goes to the local language model, which answers in one or two short sentences or, when it is clear you want an action, picks the closest command.

## How it understands you

Every sentence goes through three stages, fastest first: exact rules, a small meaning matcher (compares your sentence with example phrasings), then the language model with tool calling. A doubtful match asks "Did you mean ...?" instead of acting. Details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Where things live

| Path | What it is |
|---|---|
| `src/ultron/` | The program (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)) |
| `config/` | Files you can edit: `corrections.json` (words Whisper mishears), `pronunciations.json` (how the voice says words), `profile.example.md` |
| `models/` | Downloaded models (not in git) |
| `memory.json`, `data/activity.db`, `profile.md`, `ultron.log`, `.env` | Your private files, created on first use (not in git) |
| `docs/` | Commands, architecture, build log, wake word training |
| `tools/` | Measurement and helper scripts (speech accuracy, phrase accuracy, command list generator) |
| `tests/` | The test suite (`venv\Scripts\python.exe -m pytest -q`) |

## Privacy

Everything runs locally. The activity log stores app and project names only, in `data/activity.db`; "pause tracking" and "forget today" are voice commands. See [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Licence: [LICENSE](LICENSE).
