"""
Orchestrator: chains agents via `pipeline_full` and maps to `ProcessResponse`.

Legacy callers may still use `output_language`; it maps to english/hindi for translation.
"""

from __future__ import annotations

import logging

from app.pipeline_full import run_text_pipeline
from app.schemas import ProcessResponse
from app.source_extraction import extract_raw_from_source

logger = logging.getLogger(__name__)


def _lang_from_output_language(output_language: str) -> str:
    ol = (output_language or "").strip().lower()
    return "hindi" if ol == "hindi" else "english"


async def process_raw_text(
    raw_text: str,
    platform: str,
    tone: str,
    glossary: str = "",
    output_language: str = "match_source",
    *,
    source_kind: str = "text",
) -> ProcessResponse:
    lang = _lang_from_output_language(output_language)
    try:
        out = await run_text_pipeline(
            raw_text,
            platform,
            tone,
            lang,
            glossary=glossary,
        )
        return ProcessResponse(
            success=True,
            error=None,
            final_text=out["final_text"],
            final_english=out["final_english"],
            raw_text=out["raw_text"],
            summary=out["summary"],
            platform_draft=out["platform_draft"],
            character_validation=out["character_validation"],
            source_kind=source_kind,
            orchestrator="direct",
        )
    except Exception as e:
        logger.exception("Pipeline failed")
        return ProcessResponse(
            success=False,
            error=str(e),
            raw_text=raw_text,
            source_kind=source_kind,
        )


async def process_content(
    source: str,
    platform: str,
    tone: str,
    glossary: str = "",
    output_language: str = "match_source",
) -> ProcessResponse:
    try:
        raw_text, kind = await extract_raw_from_source(source.strip())
    except Exception as e:
        logger.exception("Extraction failed")
        return ProcessResponse(
            success=False,
            error=f"Extraction failed: {e}",
            source_kind="",
        )

    return await process_raw_text(
        raw_text,
        platform,
        tone,
        glossary=glossary,
        output_language=output_language,
        source_kind=kind,
    )
