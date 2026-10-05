"""Shared helpers for the access checks: load .env, read required settings, print results without secrets."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def setting(name: str, default: str | None = None, required: bool = True) -> str | None:
    """Return an environment value; exit with a clear message if a required one is missing."""
    value = os.environ.get(name, default)
    if required and not value:
        fail(f"{name} is not set — add it to your local .env (see docs/runbooks/).")
    return value


def masked(value: str) -> str:
    """Never print a secret: show only its length and last 2 characters."""
    return f"<{len(value)} chars, …{value[-2:]}>" if value else "<empty>"


def ok(message: str) -> None:
    print(f"OK    {message}")


def warn(message: str) -> None:
    print(f"WARN  {message}")


def fail(message: str, code: int = 1) -> None:
    print(f"FAIL  {message}")
    sys.exit(code)
