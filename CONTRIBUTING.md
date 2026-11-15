# Contributing to ULTRON

Thanks for helping. ULTRON is a local, private, voice-controlled assistant; changes should keep it that way.

## Reporting bugs and ideas

- Search the issues first, then use the Bug Report or Feature Request template.
- For bugs, include the relevant lines of `ultron.log` (it holds what was heard and the timing of each step). Remove anything private.

## Branches

- `main` is stable and changes only at the end of a phase, through a pull request from `dev`.
- `dev` is the integration branch.
- Start a feature branch from `dev` and open the pull request into `dev`. Keep commits small with honest messages.

## Setup

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install -e ".[dev,gpu]"
venv\Scripts\python.exe tools\download_voice.py
```

## Before you open a pull request

```bash
venv\Scripts\python.exe -m ruff check .
venv\Scripts\python.exe -m pytest -q
venv\Scripts\python.exe -m ultron --self-test
```

The same checks run in GitHub Actions (`.github/workflows/ci.yml`) on Windows. Rules:

- Tests never run real commands. `tests/conftest.py` puts the registry in dry-run mode; a test that needs a real handler must say so with `@pytest.mark.real_handlers` and use fakes. Do not write tests that play sound, open the microphone, load Whisper or call Ollama.
- A new voice command is one `@command` declaration in `src/ultron/commands/` (name, description, parameters, risk level, 5 to 10 example sentences). Then regenerate the list: `venv\Scripts\python.exe tools\gen_commands_txt.py` (a test fails if `docs/COMMANDS.md` is stale).
- Check phrase understanding with `venv\Scripts\python.exe tools\intent_eval.py` (add real phrasings to `tests/intents.yaml`).
- Settings belong in `src/ultron/config.py` (read from `.env`); file locations in `src/ultron/paths.py`.
- Every module starts with a short docstring saying what it is for.
- Risky actions need the spoken confirm; medium-impact ones are announced first so the user can interrupt.

## Layout

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Design decisions are recorded in [docs/BUILD_LOG.md](docs/BUILD_LOG.md).
