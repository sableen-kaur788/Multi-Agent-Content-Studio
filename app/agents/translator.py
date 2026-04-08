"""
Agent 5 — Language translator (Groq).

Translates the final social post into English or Hindi while preserving tone and facts.
"""

from __future__ import annotations

from app.groq_client import groq_client

_VALID = frozenset({"english", "hindi"})


async def translate_post(text: str, target_language: str) -> str:
    lang = target_language.strip().lower()
    if lang not in _VALID:
        raise ValueError("target_language must be english or hindi.")
    if not text or not text.strip():
        raise ValueError("Nothing to translate.")

    if lang == "english":
        prompt = f"""Translate the following social media post into clear, natural English.
Preserve meaning, tone, hashtags, line breaks, and any ---TWEET--- thread markers exactly.
Do not add commentary. Output only the translated post.

Post:
{text.strip()}
"""
    else:
        prompt = f"""Translate the following social media post into natural Hindi (Devanagari script).
Preserve meaning, tone, structure, hashtags (you may transliterate hashtags if standard),
and any ---TWEET--- thread markers exactly.
Do not add commentary. Output only the translated post.

Post:
{text.strip()}
"""

    return await groq_client.chat_complete(
        prompt,
        temperature=0.2,
        max_tokens=900,
    )
