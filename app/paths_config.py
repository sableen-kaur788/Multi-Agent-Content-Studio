"""Resolved project paths for uploads and packaged data."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = PROJECT_ROOT / "uploads"

for d in (DATA_DIR, UPLOADS_DIR):
    d.mkdir(parents=True, exist_ok=True)
