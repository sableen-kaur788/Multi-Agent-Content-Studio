"""
Agent 4 — Tone Adjuster

Rewrites the platform draft to match professional / casual / funny / empathetic tone
while preserving factual content and respecting platform character limits.
"""

from __future__ import annotations

from app.groq_client import groq_client

_VALID_TONES = frozenset({"professional", "casual", "funny", "empathetic"})


def _glossary_block(glossary: str) -> str:
    if not glossary.strip():
        return ""
    return (
        "IMPORTANT SPELLINGS TO PRESERVE EXACTLY (do not alter these names/terms):\n"
        f"{glossary.strip()}\n\n"
    )


def _language_block(output_language: str) -> str:
    if output_language == "match_source":
        return "Keep the final text in the same primary language as the draft."
    return f"Write the final text only in {output_language}."


def _tone_instructions(tone: str, platform: str) -> str:
    base = {
        "professional": (
            "Use formal vocabulary and polished sentence structure. No slang or contractions "
            "where avoidable. Stay authoritative and clear."
        ),
        "casual": (
            "Use contractions and simpler, conversational words. Sound friendly and approachable. "
            "Keep it natural, not sloppy."
        ),
        "funny": (
            "Add appropriate wit and light humor (no offensive jokes). Keep facts accurate; "
            "humor should not drown the message."
        ),
        "empathetic": (
            "Show understanding and care. Warm, supportive phrasing; acknowledge the reader. "
            "Stay sincere, not saccharine."
        ),
    }
    plat_note = {
        "twitter": (
            "Preserve Twitter rules: each segment between ---TWEET--- must be ≤280 characters. "
            "Keep the ---TWEET--- separators exactly if threading."
        ),
        "linkedin": "Keep length roughly 1200-1500 characters if the draft was in that range.",
        "instagram": "Keep length 300-500 characters including hashtags and emojis.",
    }
    return base[tone] + " " + plat_note.get(platform, "")


async def adjust_tone(
    platform_draft: str,
    platform: str,
    tone: str,
    glossary: str = "",
    output_language: str = "match_source",
    extra_instructions: str = "",
) -> str:
    """
    Rewrite the platform draft to match the requested tone while keeping facts and limits.

    Temperature 0.5, max_tokens 800. Preserves Twitter `---TWEET---` thread markers when present.
    """
    t = tone.strip().lower()
    p = platform.strip().lower()
    if t not in _VALID_TONES:
        raise ValueError(f"Unsupported tone: {tone}. Use professional, casual, funny, or empathetic.")
    if p not in ("twitter", "linkedin", "instagram"):
        raise ValueError("Invalid platform for tone adjustment.")
    if not platform_draft or not platform_draft.strip():
        raise ValueError("Platform draft is empty.")

    instructions = _tone_instructions(t, p)
    prompt = f"""Rewrite the following social draft for the specified tone and platform.

TONE GUIDANCE:
{instructions}

CONSTRAINTS:
- {_glossary_block(glossary).strip() if glossary.strip() else "Preserve names and technical terms exactly where possible."}
- {_language_block(output_language)}
- Keep the same core information and claims; do not invent facts.
- Obey platform length/structure: for Twitter, never exceed 280 chars per tweet segment; keep ---TWEET--- lines if present.
- Output ONLY the final text (no labels).

Platform: {p}
Tone: {t}

Draft:
{platform_draft.strip()}
"""
    if extra_instructions.strip():
        prompt += "\n\nADDITIONAL BRAND / STYLE RULES:\n" + extra_instructions.strip() + "\n"

    try:
        return await groq_client.chat_complete(
            prompt,
            temperature=0.5,
            max_tokens=800,
        )
    except Exception as e:
        raise RuntimeError(f"Tone adjustment (Groq) failed: {e}") from e
