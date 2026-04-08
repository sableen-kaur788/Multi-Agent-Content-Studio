"""Build simple PDF reports (final agent output + full trace). Unicode-safe for Hindi/Devanagari."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

_FONT_FAMILY = "UniRep"

# Devanagari block (Hindi, Marathi, etc.)
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def _bundled_devanagari_font() -> Path | None:
    root = Path(__file__).resolve().parent.parent / "data" / "fonts"
    vf = root / "NotoSansDevanagari-VF.ttf"
    if vf.is_file():
        return vf
    return None


def _linux_noto_regular() -> Path | None:
    p = Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf")
    return p if p.is_file() else None


def _linux_noto_devanagari_static() -> Path | None:
    p = Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf")
    return p if p.is_file() else None


def _windows_devanagari_font() -> Path | None:
    import os

    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if not fonts.is_dir():
        return None
    for name in (
        "NotoSansDevanagari-Regular.ttf",
        "Nirmala.ttf",
        "NirmalaUI.ttf",
        "mangal.ttf",
    ):
        p = fonts / name
        if p.is_file():
            return p
    return None


def _dejavu_font_path() -> Path | None:
    try:
        import fpdf

        root = Path(fpdf.__file__).resolve().parent
        for p in root.rglob("DejaVuSans.ttf"):
            return p
    except ImportError:
        pass
    return None


def _needs_devanagari(language: str, *text_parts: str) -> bool:
    if (language or "").lower().strip() == "hindi":
        return True
    blob = "\n".join(t for t in text_parts if t)
    return bool(_DEVANAGARI_RE.search(blob))


def _pick_font_path(language: str, title: str, meta_lines: list[str], body: str) -> Path | None:
    """
    Prefer system fonts (Docker installs fonts-noto-core). We avoid bundling .ttf files in the
    repo because Hugging Face may reject binary files unless Xet/LFS is configured.
    """
    meta_blob = "\n".join(meta_lines)
    if _needs_devanagari(language, title, meta_blob, body):
        for p in (
            _windows_devanagari_font(),
            _linux_noto_devanagari_static(),
        ):
            if p is not None and p.is_file():
                return p
        # No Unicode font available: fail fast instead of producing a broken Helvetica PDF.
        raise RuntimeError(
            "No Devanagari-capable font found for PDF export. "
            "On Hugging Face Docker this should be available via fonts-noto-core. "
            "On Windows install a Devanagari font (e.g. Mangal/Nirmala) and retry."
        )
    for p in (_linux_noto_regular(), _dejavu_font_path()):
        if p is not None and p.is_file():
            return p
    return _dejavu_font_path()


def _pdf_to_bytes(pdf: object) -> bytes:
    bio = BytesIO()
    pdf.output(bio)  # type: ignore[attr-defined]
    return bio.getvalue()


def _pdf_bytes(title: str, meta_lines: list[str], body: str, *, language: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    path = _pick_font_path(language, title, meta_lines, body)
    use_uni = False
    if path and path.is_file():
        try:
            pdf.add_font(_FONT_FAMILY, "", str(path))
            use_uni = True
        except Exception:
            use_uni = False

    def set_font(size: int) -> None:
        if use_uni:
            pdf.set_font(_FONT_FAMILY, size=size)
        else:
            pdf.set_font("Helvetica", size=size)

    set_font(14)
    pdf.multi_cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    set_font(9)
    for line in meta_lines:
        pdf.multi_cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    set_font(11)
    pdf.multi_cell(0, 6, body or "(empty)", new_x="LMARGIN", new_y="NEXT")

    pdf.set_title(title[:120])
    return _pdf_to_bytes(pdf)


def final_report_pdf(
    final_text: str,
    *,
    platform: str,
    tone: str,
    language: str,
    source_hint: str,
) -> bytes:
    """PDF for the last pipeline stage output (tone / translate)."""
    meta = [
        f"Platform: {platform}",
        f"Tone: {tone}",
        f"Language: {language}",
        f"Source: {source_hint}",
        "",
        "Final post from the tone adjuster and translator (if Hindi).",
    ]
    return _pdf_bytes("Final report", meta, final_text.strip(), language=language)


def trace_report_pdf(trace_text: str, *, language: str) -> bytes:
    """PDF of the full agent-by-agent trace."""
    meta = [
        "All agents: extractor through tone (and translator if applicable).",
    ]
    return _pdf_bytes("Full agent trace", meta, trace_text.strip(), language=language)


def agent_step_pdf(
    short: str,
    full_title: str,
    body: str,
    *,
    language: str,
) -> bytes:
    """Single-agent PDF (one step of the pipeline)."""
    meta = [
        f"Step: {short}",
        "This PDF contains only this agent’s output.",
    ]
    return _pdf_bytes(full_title, meta, body.strip(), language=language)
