"""Resolve textual `source` into raw text (URL or local PDF path)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.agents.extractor import extract_content
from app.paths_config import PROJECT_ROOT, UPLOADS_DIR
from app.validators import is_likely_blog_url, is_likely_youtube_url


def _allowed_path(path: Path) -> Path:
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    uploads = UPLOADS_DIR.resolve()
    for base in (uploads, root):
        try:
            resolved.relative_to(base)
            return resolved
        except ValueError:
            continue
    if os.getenv("ALLOW_ABSOLUTE_MEDIA_PATHS", "").lower() in ("1", "true", "yes"):
        return resolved
    raise ValueError(
        "Local file paths must be inside the project folder or uploads/. "
        "Set ALLOW_ABSOLUTE_MEDIA_PATHS=1 to allow other paths (use with care)."
    )


async def _extract_pdf_path(path: Path) -> str:
    def _read() -> str:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()

    text = await asyncio.to_thread(_read)
    if text:
        return text
    from app.ocr import ocr_pdf_bytes_to_text

    data = await asyncio.to_thread(path.read_bytes)

    def _ocr() -> str:
        return ocr_pdf_bytes_to_text(data, max_pages=50)

    return await asyncio.to_thread(_ocr)


async def extract_raw_from_source(source: str) -> tuple[str, str]:
    """
    Returns (raw_text, source_kind) where source_kind is
    youtube | blog | pdf_path.
    """
    s = source.strip()
    if not s:
        raise ValueError("source is empty")

    p = Path(s)
    if p.exists() and p.is_file():
        safe = _allowed_path(p)
        suf = safe.suffix.lower()
        if suf == ".pdf":
            return (await _extract_pdf_path(safe), "pdf_path")
        raise ValueError(f"Unsupported file type: {suf}")

    if is_likely_youtube_url(s) or is_likely_blog_url(s):
        text = await extract_content(s)
        kind = "youtube" if is_likely_youtube_url(s) else "blog"
        return text, kind

    raise ValueError(
        "source must be a YouTube URL, blog URL, or an existing path to PDF "
        "under the project or uploads/ directory."
    )
