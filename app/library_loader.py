"""Load YAML template and brand profile libraries."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.paths_config import DATA_DIR


@lru_cache
def load_templates() -> dict[str, Any]:
    p = DATA_DIR / "templates.yaml"
    if not p.exists():
        return {"templates": {}}
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"templates": {}}


@lru_cache
def load_brand_profiles() -> dict[str, Any]:
    p = DATA_DIR / "brand_profiles.yaml"
    if not p.exists():
        return {"profiles": {}}
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"profiles": {}}


def get_brand_hints(profile_key: str | None) -> str:
    if not profile_key:
        return ""
    profiles = load_brand_profiles().get("profiles") or {}
    prof = profiles.get(profile_key.strip())
    if not prof:
        return ""
    return (
        f"Brand voice hints ({profile_key}): "
        f"preferred tone vibe={prof.get('tone_hint', '')}, "
        f"emoji_density={prof.get('emoji_density', '')}, "
        f"target_hashtag_count≈{prof.get('hashtag_count', '')}.\n"
    )


def format_template(platform: str, template_key: str, variables: dict[str, str]) -> str | None:
    lib = load_templates().get("templates") or {}
    entry = lib.get(template_key)
    if not entry or not isinstance(entry, dict):
        return None
    tpl = entry.get(platform) or entry.get("default")
    if not tpl:
        return None
    try:
        return tpl.format(**variables)
    except Exception:
        return None
