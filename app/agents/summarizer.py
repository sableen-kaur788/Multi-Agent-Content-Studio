"""
Agent 2 — Summarizer

Turns long raw text into a tight bullet summary (max ~300 words in output)
using Groq with low temperature for consistency.
"""

from __future__ import annotations

from app.groq_client import groq_client

_SUMMARY_PROMPT_PREFIX = (
    "Extract key bullet points from this content. Keep the core message.\n"
    "Produce between 5 and 15 bullet points. Total length roughly 200-300 words.\n"
    "Return only the bullets (use '- ' or '* '), with no preamble or closing remarks.\n\n"
)


def _split_text(text: str, chunk_chars: int = 9000) -> list[str]:
    parts: list[str] = []
    s = text.strip()
    while s:
        if len(s) <= chunk_chars:
            parts.append(s)
            break
        cut = s.rfind("\n", 0, chunk_chars)
        if cut < chunk_chars * 0.5:
            cut = chunk_chars
        parts.append(s[:cut].strip())
        s = s[cut:].strip()
    return [p for p in parts if p]


def _glossary_block(glossary: str) -> str:
    if not glossary.strip():
        return ""
    return (
        "IMPORTANT SPELLINGS TO PRESERVE EXACTLY (do not correct/alter):\n"
        f"{glossary.strip()}\n\n"
    )


def _language_block(output_language: str) -> str:
    if output_language == "match_source":
        return "LANGUAGE REQUIREMENT: Keep output in the same primary language as the source content.\n\n"
    return f"LANGUAGE REQUIREMENT: Write output only in {output_language}.\n\n"


async def summarize_text(
    raw_text: str, glossary: str = "", output_language: str = "match_source"
) -> str:
    """
    Produce bullet-only summary via Groq (temperature from GROQ_TEMPERATURE, max_tokens 500).

    Raises ValueError for empty input; RuntimeError when the Groq call fails after retries.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Cannot summarize empty text.")
    try:
        temperature = 0.3
        chunks = _split_text(raw_text.strip(), chunk_chars=9000)

        # Small/normal documents: single-pass summary.
        if len(chunks) == 1:
            prompt = (
                _SUMMARY_PROMPT_PREFIX
                + _language_block(output_language)
                + _glossary_block(glossary)
                + "Content:\n"
                + chunks[0]
            )
            return await groq_client.chat_complete(
                prompt,
                temperature=temperature,
                max_tokens=500,
            )

        # Large documents: hierarchical summarization to stay under model limits.
        partials: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            partial_prompt = (
                _SUMMARY_PROMPT_PREFIX
                + _language_block(output_language)
                + _glossary_block(glossary)
                + f"This is chunk {idx}/{len(chunks)}.\n\nContent:\n{chunk}"
            )
            partial = await groq_client.chat_complete(
                partial_prompt,
                temperature=temperature,
                max_tokens=350,
            )
            partials.append(partial.strip())

        final_prompt = (
            _SUMMARY_PROMPT_PREFIX
            + _language_block(output_language)
            + _glossary_block(glossary)
            + "Combine these chunk summaries into one final concise bullet summary.\n\n"
            + "Chunk summaries:\n"
            + "\n\n".join(partials)
        )
        return await groq_client.chat_complete(
            final_prompt,
            temperature=temperature,
            max_tokens=500,
        )
    except Exception as e:
        raise RuntimeError(f"Summarization (Groq) failed: {e}") from e
