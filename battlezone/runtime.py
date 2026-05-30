import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GAME_ENTRYPOINT = PROJECT_ROOT / "battlezone_game.py"


def merged_env(overrides=None):
    env = os.environ.copy()
    if overrides:
        env.update({key: str(value) for key, value in overrides.items() if value is not None})
    return env


def run_game(overrides=None):
    if not GAME_ENTRYPOINT.exists():
        raise FileNotFoundError("Could not find {}".format(GAME_ENTRYPOINT))
    return subprocess.call([sys.executable, str(GAME_ENTRYPOINT)], cwd=str(PROJECT_ROOT), env=merged_env(overrides))
