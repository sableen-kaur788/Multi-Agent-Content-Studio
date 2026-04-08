"""
Agent 3 — Platform Adapter

Maps the bullet summary into a platform-specific draft:
- Twitter: ≤280 chars per tweet; 1–3 hashtags; use a thread (one tweet per line)
  separated by the marker ---TWEET--- if over 280 characters total.
- LinkedIn: professional, 1200–1500 characters, 3–5 hashtags, line breaks.
- Instagram: hook, 300–500 characters, emojis, 5–10 hashtags.
"""

from __future__ import annotations

from app.groq_client import groq_client

_VALID_PLATFORMS = frozenset({"twitter", "linkedin", "instagram"})


def _glossary_block(glossary: str) -> str:
    if not glossary.strip():
        return ""
    return (
        "\nIMPORTANT SPELLINGS TO PRESERVE EXACTLY (do not alter):\n"
        f"{glossary.strip()}\n"
    )


def _language_block(output_language: str) -> str:
    if output_language == "match_source":
        return "\nLANGUAGE REQUIREMENT: Keep output in the same primary language as the summary.\n"
    return f"\nLANGUAGE REQUIREMENT: Write output only in {output_language}.\n"


def _twitter_prompt(summary: str) -> str:
    return f"""You are a social copywriter. Turn the summary into Twitter content.

RULES:
- Each tweet must be at most 280 characters (including spaces and hashtags).
- Use 1-3 relevant hashtags total across the thread (not per tweet if that breaks limit).
- If the full message cannot fit in one tweet, write a THREAD: multiple tweets separated ONLY by the exact line ---TWEET--- (on its own line between tweets).
- No URLs unless present in the summary.
- Do not add preamble like "Here is your tweet".

Summary:
{summary}

Output only the tweet(s), with ---TWEET--- between tweets if needed."""


def _linkedin_prompt(summary: str) -> str:
    return f"""You are a LinkedIn content strategist. Turn the summary into a single LinkedIn post.

RULES:
- Professional, clear tone.
- Target length 1200-1500 characters (including hashtags and line breaks). Stay within this range if possible.
- Include 3-5 professional hashtags at the end.
- Use short paragraphs and line breaks for readability.
- No markdown headings; plain text only.
- Do not add an introduction like "Here is a post".

Summary:
{summary}

Output only the LinkedIn post text."""


def _instagram_prompt(summary: str) -> str:
    return f"""You are an Instagram caption writer. Turn the summary into one caption.

RULES:
- Engaging opening hook in the first line.
- Total length 300-500 characters including emojis and hashtags.
- Use relevant emojis sparingly but effectively.
- Include 5-10 hashtags at the end (count toward character limit).
- No markdown.

Summary:
{summary}

Output only the Instagram caption."""


async def adapt_for_platform(
    summary: str,
    platform: str,
    glossary: str = "",
    output_language: str = "match_source",
    extra_instructions: str = "",
) -> str:
    """
    Turn bullet summary into a first-draft social post for one platform.

    Temperature 0.4 and max_tokens 800. Raises ValueError for unknown platform or empty summary.
    """
    p = platform.strip().lower()
    if p not in _VALID_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}. Use twitter, linkedin, or instagram.")

    if not summary or not summary.strip():
        raise ValueError("Summary is empty; cannot adapt.")

    if p == "twitter":
        prompt = (
            _twitter_prompt(summary.strip())
            + _glossary_block(glossary)
            + _language_block(output_language)
        )
    elif p == "linkedin":
        prompt = (
            _linkedin_prompt(summary.strip())
            + _glossary_block(glossary)
            + _language_block(output_language)
        )
    else:
        prompt = (
            _instagram_prompt(summary.strip())
            + _glossary_block(glossary)
            + _language_block(output_language)
        )

    if extra_instructions.strip():
        prompt += "\n\nADDITIONAL BRAND / STYLE RULES:\n" + extra_instructions.strip() + "\n"

    try:
        return await groq_client.chat_complete(
            prompt,
            temperature=0.4,
            max_tokens=800,
        )
    except Exception as e:
        raise RuntimeError(f"Platform adaptation (Groq) failed: {e}") from e
