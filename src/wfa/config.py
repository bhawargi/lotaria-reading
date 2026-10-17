"""Settings from a `.env` file (see `.env.example` for the names).

`.env` is looked up from the current directory upwards and is gitignored. Values already set
in the environment win, so an `export` in the shell still overrides the file.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv


def load_env() -> None:
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)
