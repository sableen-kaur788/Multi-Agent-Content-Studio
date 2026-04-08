"""
Optional CrewAI sequential crew wrapping the same Groq-backed tools.

Runs inside a worker thread from FastAPI so tool `asyncio.run(...)` calls are safe.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from app.config import get_settings
from app.source_extraction import extract_raw_from_source

logger = logging.getLogger(__name__)


def _run_coro(coro):
    return asyncio.run(coro)


def run_crewai_pipeline(
    source: str,
    platform: str,
    tone: str,
    language: str,
    glossary: str = "",
    brand_profile: str | None = None,
    template_id: str | None = None,
    template_variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        from crewai import LLM
        from crewai import Agent, Crew, Process, Task
        from crewai.tools import BaseTool
        from pydantic import BaseModel, Field
    except ImportError as e:
        raise RuntimeError(
            "crewai is not installed. pip install crewai litellm"
        ) from e

    settings = get_settings()
    key = (settings.get("groq_api_key") or "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is required for CrewAI + Groq.")
    os.environ.setdefault("GROQ_API_KEY", key)

    model_id = (settings.get("groq_model") or "llama-3.1-8b-instant").strip()
    if "/" not in model_id:
        model_id = f"groq/{model_id}"

    llm = LLM(model=model_id, api_key=key, temperature=0.3)

    class ExtractInput(BaseModel):
        source: str = Field(..., description="YouTube/blog URL or media path")

    class ExtractTool(BaseTool):
        name: str = "extract_raw_source"
        description: str = "Extract raw text from YouTube, blog, PDF path, image, or video path."
        args_schema: type[BaseModel] = ExtractInput

        def _run(self, source: str) -> str:
            raw, kind = _run_coro(extract_raw_from_source(source))
            return f"[source_kind={kind}]\n{raw}"

    class SummarizeInput(BaseModel):
        raw_text: str = Field(...)
        glossary: str = Field(default="")

    class SummarizeTool(BaseTool):
        name: str = "summarize_bullets"
        description: str = "Summarize raw text into 5-15 English bullet points."
        args_schema: type[BaseModel] = SummarizeInput

        def _run(self, raw_text: str, glossary: str = "") -> str:
            from app.agents.summarizer import summarize_text

            return _run_coro(
                summarize_text(raw_text, glossary=glossary, output_language="english")
            )

    class AdaptInput(BaseModel):
        summary: str = Field(...)
        platform: str = Field(...)
        glossary: str = Field(default="")
        brand_hint: str = Field(default="")

    class AdaptTool(BaseTool):
        name: str = "platform_adapt"
        description: str = "Turn summary into a platform-specific draft (English)."
        args_schema: type[BaseModel] = AdaptInput

        def _run(
            self, summary: str, platform: str, glossary: str = "", brand_hint: str = ""
        ) -> str:
            from app.agents.platform_adapter import adapt_for_platform

            return _run_coro(
                adapt_for_platform(
                    summary,
                    platform,
                    glossary=glossary,
                    output_language="english",
                    extra_instructions=brand_hint,
                )
            )

    class ToneInput(BaseModel):
        draft: str = Field(...)
        platform: str = Field(...)
        tone: str = Field(...)
        glossary: str = Field(default="")
        brand_hint: str = Field(default="")

    class ToneTool(BaseTool):
        name: str = "tone_adjust"
        description: str = "Adjust tone of the draft while keeping platform rules."
        args_schema: type[BaseModel] = ToneInput

        def _run(
            self,
            draft: str,
            platform: str,
            tone: str,
            glossary: str = "",
            brand_hint: str = "",
        ) -> str:
            from app.agents.tone_adjuster import adjust_tone

            return _run_coro(
                adjust_tone(
                    draft,
                    platform,
                    tone,
                    glossary=glossary,
                    output_language="english",
                    extra_instructions=brand_hint,
                )
            )

    class TranslateInput(BaseModel):
        text: str = Field(...)
        language: str = Field(..., description="english or hindi")

    class TranslateTool(BaseTool):
        name: str = "translate_post"
        description: str = "Translate final post to English or Hindi."
        args_schema: type[BaseModel] = TranslateInput

        def _run(self, text: str, language: str) -> str:
            language = language.strip().lower()
            if language == "english":
                return text.strip()
            from app.agents.translator import translate_post

            return _run_coro(translate_post(text, "hindi"))

    from app.library_loader import get_brand_hints

    brand_hint = get_brand_hints(brand_profile)

    agent_extract = Agent(
        role="Content Extractor",
        goal="Extract complete raw text from the given source.",
        backstory="You extract transcripts, articles, PDF text, or media descriptions.",
        tools=[ExtractTool()],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )
    agent_summ = Agent(
        role="Summarizer",
        goal="Produce concise English bullet summaries.",
        backstory="You distill content into 5-15 bullets.",
        tools=[SummarizeTool()],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )
    agent_adapt = Agent(
        role="Platform Strategist",
        goal="Draft platform-specific posts in English.",
        backstory="You know Twitter, LinkedIn, and Instagram constraints.",
        tools=[AdaptTool()],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )
    agent_tone = Agent(
        role="Tone Editor",
        goal="Rewrite drafts to match requested tone.",
        backstory="You preserve facts and character limits.",
        tools=[ToneTool()],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )
    agent_lang = Agent(
        role="Translator",
        goal="Translate or polish the final post for the target language.",
        backstory="You keep structure and hashtags stable.",
        tools=[TranslateTool()],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    task1 = Task(
        description=(
            f"Use the extract tool once with source={source!r}. "
            "Return ONLY the tool output text (strip any [source_kind=...] prefix lines if redundant)."
        ),
        expected_output="Raw extracted text",
        agent=agent_extract,
    )
    task2 = Task(
        description=(
            "From the previous task output, call summarize_bullets with that full text as raw_text "
            f"and glossary={glossary!r}. Return only bullet text."
        ),
        expected_output="Bullet summary in English",
        agent=agent_summ,
        context=[task1],
    )
    task3 = Task(
        description=(
            "Call platform_adapt with summary=<previous task output>, "
            f"platform={platform!r}, glossary={glossary!r}, brand_hint={brand_hint!r}."
        ),
        expected_output="Platform draft English",
        agent=agent_adapt,
        context=[task2],
    )
    task4 = Task(
        description=(
            "Call tone_adjust with draft=<previous output>, "
            f"platform={platform!r}, tone={tone!r}, glossary={glossary!r}, brand_hint={brand_hint!r}."
        ),
        expected_output="Tone-adjusted English post",
        agent=agent_tone,
        context=[task3],
    )
    task5 = Task(
        description=(
            "Call translate_post with text=<previous output> and "
            f"language={language!r}."
        ),
        expected_output="Final post in target language",
        agent=agent_lang,
        context=[task4],
    )

    crew = Crew(
        agents=[agent_extract, agent_summ, agent_adapt, agent_tone, agent_lang],
        tasks=[task1, task2, task3, task4, task5],
        process=Process.sequential,
        verbose=False,
    )
    result = crew.kickoff()
    final_text = str(result.raw if hasattr(result, "raw") else result)

    from app.library_loader import format_template

    if template_id:
        tpl = format_template(platform, template_id, template_variables or {})
        if tpl:
            final_text = f"{tpl.strip()}\n\n{final_text.strip()}"

    return {
        "raw_text": "",
        "summary": "",
        "platform_draft": "",
        "final_english": "",
        "final_text": final_text.strip(),
        "character_validation": {},
        "source_kind": "crewai",
        "used_crewai": True,
        "crew_debug": str(result),
    }
