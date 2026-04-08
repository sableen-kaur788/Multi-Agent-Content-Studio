"""Shared formatting for agent pipeline trace (Streamlit UI)."""

from __future__ import annotations

from typing import Any

MAX_PREVIEW_CHARS = 12_000


def format_agent_pipeline_view(out: dict[str, Any]) -> str:
    """Human-readable trace: extractor → summarizer → platform → tone → (translator)."""
    blocks: list[str] = []
    sk = out.get("source_kind")
    blocks.append("=== Agent 1 · Content extractor ===")
    if sk:
        blocks.append(f"Source kind: {sk}")
    else:
        blocks.append("Source: PDF upload (text extracted in the app; OCR used if needed)")
    raw = (out.get("raw_text") or "").strip()
    if len(raw) > MAX_PREVIEW_CHARS:
        blocks.append(
            raw[:MAX_PREVIEW_CHARS]
            + f"\n\n… [truncated; full raw_text is {len(out.get('raw_text') or '')} characters]"
        )
    else:
        blocks.append(raw or "(empty)")

    blocks.append("\n=== Agent 2 · Summarizer ===")
    blocks.append((out.get("summary") or "").strip() or "(empty)")

    blocks.append("\n=== Agent 3 · Platform adapter ===")
    blocks.append((out.get("platform_draft") or "").strip() or "(empty)")

    blocks.append("\n=== Agent 4 · Tone adjuster (English) ===")
    blocks.append((out.get("final_english") or "").strip() or "(empty)")

    final = (out.get("final_text") or "").strip()
    final_en = (out.get("final_english") or "").strip()
    if final and final != final_en:
        blocks.append("\n=== Agent 5 · Translator ===")
        blocks.append(final)

    cv = out.get("character_validation")
    if cv:
        blocks.append("\n=== Character / length checks ===")
        blocks.append(str(cv))

    return "\n".join(blocks)


def pipeline_step_panels(out: dict[str, Any]) -> list[tuple[str, str, str]]:
    """
    Build panels for interactive UI: (short_label, full_title, body_text).

    short_label is used in chips; full_title in expanders.
    """
    panels: list[tuple[str, str, str]] = []
    sk = out.get("source_kind")
    meta = f"Source kind: {sk}" if sk else "Source: PDF upload (text or OCR)"
    raw = (out.get("raw_text") or "").strip()
    if len(raw) > MAX_PREVIEW_CHARS:
        body = (
            f"{meta}\n\n"
            f"{raw[:MAX_PREVIEW_CHARS]}\n\n"
            f"… [truncated; full raw_text is {len(out.get('raw_text') or '')} characters]"
        )
    else:
        body = f"{meta}\n\n{raw or '(empty)'}"
    panels.append(("Extract", "Agent 1 · Content extractor", body))

    panels.append(
        ("Summarize", "Agent 2 · Summarizer", (out.get("summary") or "").strip() or "(empty)")
    )
    panels.append(
        (
            "Platform",
            "Agent 3 · Platform adapter",
            (out.get("platform_draft") or "").strip() or "(empty)",
        )
    )
    panels.append(
        (
            "Tone",
            "Agent 4 · Tone adjuster (English)",
            (out.get("final_english") or "").strip() or "(empty)",
        )
    )
    final = (out.get("final_text") or "").strip()
    final_en = (out.get("final_english") or "").strip()
    if final and final != final_en:
        panels.append(("Translate", "Agent 5 · Translator", final))

    cv = out.get("character_validation")
    if cv:
        panels.append(("Checks", "Character / length validation", str(cv)))

    return panels
