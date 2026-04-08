"""Application configuration loaded from environment variables.

We explicitly load a `.env` from the project root (one folder above `app/`)
so running via uvicorn from different working directories still works.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project-root .env (agent/.env)
_ROOT_ENV = Path(__file__).resolve().parents[1] / ".env"


def _load_env() -> None:
    """
    Load environment variables from the project-root `.env`.

    We call this both at import time and inside `get_settings()` so that:
    - Changes to `.env` are picked up even if the reloader doesn't fully restart.
    - A stale OS-level GROQ_API_KEY does not override the `.env` value.
    """
    if _ROOT_ENV.exists():
        load_dotenv(dotenv_path=_ROOT_ENV, override=True)
    else:
        load_dotenv(override=True)


_load_env()

def get_env_diagnostics() -> dict:
    """
    Non-secret diagnostics to verify where `.env` is being loaded from.
    """
    try:
        exists = _ROOT_ENV.exists()
        size = _ROOT_ENV.stat().st_size if exists else 0
    except Exception:
        exists = False
        size = 0
    return {
        "root_env_path": str(_ROOT_ENV),
        "root_env_exists": exists,
        "root_env_size_bytes": size,
    }


def get_settings() -> dict:
    """
    Read settings from the current environment.

    Note: we intentionally do NOT cache this so editing `.env` + restarting uvicorn
    always reflects the latest values, and local debugging is less confusing.
    """
    _load_env()
    return {
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "groq_model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        "groq_temperature_default": float(os.getenv("GROQ_TEMPERATURE", "0.3")),
    }
