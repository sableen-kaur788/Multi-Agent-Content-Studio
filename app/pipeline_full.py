"""End-to-end pipeline: extract → summarize → adapt → tone → translate."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.platform_adapter import adapt_for_platform
from app.agents.summarizer import summarize_text
from app.agents.tone_adjuster import adjust_tone
from app.agents.translator import translate_post
from app.library_loader import format_template, get_brand_hints
from app.platform_validation import validate_both_stages
from app.source_extraction import extract_raw_from_source

logger = logging.getLogger(__name__)


async def run_text_pipeline(
    raw_text: str,
    platform: str,
    tone: str,
    language: str,
    *,
    glossary: str = "",
    brand_profile: str | None = None,
    template_id: str | None = None,
    template_variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    lang = language.strip().lower()
    brand = get_brand_hints(brand_profile)

    summary = await summarize_text(
        raw_text, glossary=glossary, output_language="english"
    )
    platform_draft = await adapt_for_platform(
        summary,
        platform,
        glossary=glossary,
        output_language="english",
        extra_instructions=brand,
    )
    final_en = await adjust_tone(
        platform_draft,
        platform,
        tone,
        glossary=glossary,
        output_language="english",
        extra_instructions=brand,
    )

    if template_id:
        tpl = format_template(platform, template_id, template_variables or {})
        if tpl:
            final_en = f"{tpl.strip()}\n\n{final_en.strip()}"

    if lang == "english":
        final_out = final_en.strip()
    elif lang == "hindi":
        final_out = (await translate_post(final_en, "hindi")).strip()
    else:
        raise ValueError("language must be english or hindi")

    validation = validate_both_stages(platform, platform_draft, final_en)
    return {
        "raw_text": raw_text,
        "summary": summary,
        "platform_draft": platform_draft,
        "final_english": final_en,
        "final_text": final_out,
        "character_validation": validation,
    }


async def run_from_source(
    source: str,
    platform: str,
    tone: str,
    language: str,
    **kwargs: Any,
) -> dict[str, Any]:
    raw_text, source_kind = await extract_raw_from_source(source)
    out = await run_text_pipeline(
        raw_text, platform, tone, language, **kwargs
    )
    out["source_kind"] = source_kind
    return out
