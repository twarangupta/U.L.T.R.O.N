"""Where ULTRON keeps its files. Every other module gets its paths from here.

ROOT is the project folder (the one holding src/, config/ and models/). Nothing
is stored inside src/, so moving code around never moves your data.

    config/   files you may edit: corrections.json, pronunciations.json, profile.example.md
    models/   downloaded models (git-ignored)
    data/     activity log database (git-ignored)
    memory.json, profile.md, ultron.log, .env   your private files at ROOT (git-ignored)
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(ROOT, "config")
MODELS_DIR = os.path.join(ROOT, "models")
DATA_DIR = os.path.join(ROOT, "data")
LOG_FILE = os.path.join(ROOT, "ultron.log")
MEMORY_FILE = os.path.join(ROOT, "memory.json")
PROFILE_FILE = os.path.join(ROOT, "profile.md")
