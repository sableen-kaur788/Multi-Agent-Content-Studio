"""
Character-count and structure validation for platform-specific outputs.

Used after Agent 3 and Agent 4 to verify drafts respect platform constraints.
"""

from __future__ import annotations

import re

_TWITTER_SPLIT = re.compile(r"^\s*---TWEET---\s*$", re.MULTILINE)


def _split_twitter_segments(text: str) -> list[str]:
    parts = _TWITTER_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def validate_platform_output(platform: str, text: str) -> dict:
    """
    Return a dict with valid flag, character counts, and human-readable notes.

    - Twitter: each tweet segment (split on ---TWEET---) must be <= 280 chars.
    - LinkedIn: ideal range 1200-1500 chars (soft validation: valid if 800-2500 to allow LLM variance).
    - Instagram: 300-500 chars inclusive.
    """
    p = platform.strip().lower()
    stripped = (text or "").strip()
    length = len(stripped)

    if p == "twitter":
        segments = _split_twitter_segments(stripped) or ([stripped] if stripped else [])
        seg_lengths = [len(s) for s in segments]
        over = [i for i, ln in enumerate(seg_lengths, start=1) if ln > 280]
        return {
            "platform": p,
            "valid": len(over) == 0 and len(segments) > 0,
            "total_characters": length,
            "segment_count": len(segments),
            "segment_lengths": seg_lengths,
            "violations": [f"Segment {i} exceeds 280 characters ({seg_lengths[i-1]})." for i in over],
        }

    if p == "linkedin":
        in_ideal = 1200 <= length <= 1500
        in_soft = 800 <= length <= 2500
        return {
            "platform": p,
            "valid": in_soft,
            "total_characters": length,
            "in_ideal_range_1200_1500": in_ideal,
            "violations": []
            if in_soft
            else [
                f"Length {length} is outside acceptable soft bounds (800-2500). "
                "Target 1200-1500 for best LinkedIn performance."
            ],
        }

    if p == "instagram":
        ok = 300 <= length <= 500
        return {
            "platform": p,
            "valid": ok,
            "total_characters": length,
            "violations": []
            if ok
            else [f"Length {length} is outside required 300-500 character range."],
        }

    return {
        "platform": p,
        "valid": False,
        "total_characters": length,
        "violations": [f"Unknown platform for validation: {platform}"],
    }


def validate_both_stages(
    platform: str, draft_text: str, final_text: str
) -> dict:
    """Validate Agent 3 draft and Agent 4 final output side by side."""
    return {
        "after_platform_adapter": validate_platform_output(platform, draft_text),
        "after_tone_adjuster": validate_platform_output(platform, final_text),
    }
