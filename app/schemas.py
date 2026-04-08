"""Pydantic request/response models for the public API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ProcessRequest(BaseModel):
    """POST /process JSON (multi-source pipeline)."""

    source: str = Field(
        ...,
        description="YouTube URL, blog URL, or path to PDF/image/video under project/uploads",
    )
    platform: str = Field(..., description="twitter | linkedin | instagram")
    tone: str = Field(..., description="professional | casual | funny | empathetic")
    language: Literal["english", "hindi"] = "english"
    glossary: str = ""
    brand_profile: str | None = None
    template_id: str | None = None
    template_variables: dict[str, str] = Field(default_factory=dict)
    orchestrator: Literal["direct", "crewai"] = "direct"
    output_language: str | None = Field(
        default=None,
        description="Deprecated: if set to hindi, maps to language=hindi",
    )

    @field_validator("source", "platform", "tone", "glossary", mode="before")
    @classmethod
    def strip_str(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("brand_profile", "template_id", mode="before")
    @classmethod
    def strip_opt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("platform")
    @classmethod
    def platform_ok(cls, v: str) -> str:
        p = v.lower()
        if p not in ("twitter", "linkedin", "instagram"):
            raise ValueError("platform must be twitter, linkedin, or instagram")
        return p

    @field_validator("tone")
    @classmethod
    def tone_ok(cls, v: str) -> str:
        t = v.lower()
        if t not in ("professional", "casual", "funny", "empathetic"):
            raise ValueError("tone must be professional, casual, funny, or empathetic")
        return t

    @model_validator(mode="after")
    def legacy_lang(self) -> ProcessRequest:
        if self.output_language:
            ol = self.output_language.strip().lower()
            if ol == "hindi":
                self.language = "hindi"
        return self


class ProcessResponse(BaseModel):
    """Unified pipeline response."""

    success: bool = True
    error: str | None = None
    final_text: str = ""
    final_english: str = ""
    raw_text: str = ""
    summary: str = ""
    platform_draft: str = ""
    character_validation: dict[str, Any] = Field(default_factory=dict)
    source_kind: str = ""
    orchestrator: str = "direct"
    crew_notes: str | None = None


class BatchProcessRequest(BaseModel):
    source: str
    platforms: list[str] = Field(..., min_length=1)
    tones: list[str] = Field(..., min_length=1)
    languages: list[str] = Field(..., min_length=1)
    webhook_url: str | None = None
    glossary: str = ""
    brand_profile: str | None = None

    @field_validator("source", "glossary", "webhook_url", "brand_profile", mode="before")
    @classmethod
    def strip_fields(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip()

    @field_validator("platforms", "tones", "languages")
    @classmethod
    def lower_lists(cls, v: list[str]) -> list[str]:
        return [x.strip().lower() for x in v]

    @field_validator("platforms")
    @classmethod
    def platforms_allowed(cls, v: list[str]) -> list[str]:
        ok = {"twitter", "linkedin", "instagram"}
        for p in v:
            if p not in ok:
                raise ValueError(f"Invalid platform: {p}")
        return v

    @field_validator("tones")
    @classmethod
    def tones_allowed(cls, v: list[str]) -> list[str]:
        ok = {"professional", "casual", "funny", "empathetic"}
        for t in v:
            if t not in ok:
                raise ValueError(f"Invalid tone: {t}")
        return v

    @field_validator("languages")
    @classmethod
    def languages_allowed(cls, v: list[str]) -> list[str]:
        ok = {"english", "hindi"}
        for lang in v:
            if lang not in ok:
                raise ValueError(f"Invalid language: {lang}")
        return v


class BatchProcessResponse(BaseModel):
    job_id: str
    status: str = "queued"


class BatchJobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


class ReviewStartRequest(BaseModel):
    source: str
    platform: str
    tone: str
    language: Literal["english", "hindi"] = "english"
    glossary: str = ""
    brand_profile: str | None = None

    @field_validator("source", "glossary", mode="before")
    @classmethod
    def strip_s(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("brand_profile", mode="before")
    @classmethod
    def strip_bp(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("platform")
    @classmethod
    def platform_ok(cls, v: str) -> str:
        p = v.strip().lower()
        if p not in ("twitter", "linkedin", "instagram"):
            raise ValueError("platform must be twitter, linkedin, or instagram")
        return p

    @field_validator("tone")
    @classmethod
    def tone_ok(cls, v: str) -> str:
        t = v.strip().lower()
        if t not in ("professional", "casual", "funny", "empathetic"):
            raise ValueError("tone must be professional, casual, funny, or empathetic")
        return t


class ReviewStartResponse(BaseModel):
    review_id: str
    summary: str
    raw_text: str
    source_kind: str


class ReviewSummarySubmit(BaseModel):
    summary: str


class ReviewSummaryResponse(BaseModel):
    review_id: str
    platform_draft: str
    final_english: str


class ReviewFinalSubmit(BaseModel):
    final_english: str


class ReviewFinalResponse(BaseModel):
    review_id: str
    final_text: str


class HealthResponse(BaseModel):
    status: str = "ok"


class ModelsResponse(BaseModel):
    models: list[dict[str, str]]
    target_model: str
    target_model_available: bool
