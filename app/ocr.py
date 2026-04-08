"""
Optional OCR fallback for scanned PDFs.

If a PDF contains only images (no embedded text), `pypdf` extraction returns empty.
This module provides an OCR pipeline that is only used when the optional
dependencies are installed:

- pdf2image
- pytesseract

On Windows, pdf2image typically also requires Poppler to be installed and on PATH.
"""

from __future__ import annotations

import os
from typing import Any


def ocr_runtime_status() -> dict[str, Any]:
    """
    Return non-secret OCR readiness diagnostics for UI/debugging.
    """
    status: dict[str, Any] = {
        "pdf2image_installed": False,
        "pytesseract_installed": False,
        "tesseract_cmd": "",
        "tesseract_available": False,
        "poppler_path": "",
        "ready": False,
        "notes": [],
    }

    try:
        from pdf2image import convert_from_bytes  # noqa: F401
        status["pdf2image_installed"] = True
    except Exception:
        status["notes"].append("Install pdf2image via pip.")

    try:
        import pytesseract

        status["pytesseract_installed"] = True
        tess_cmd = os.getenv("TESSERACT_CMD", "").strip()
        status["tesseract_cmd"] = tess_cmd
        if tess_cmd:
            pytesseract.pytesseract.tesseract_cmd = tess_cmd
        try:
            _ = pytesseract.get_tesseract_version()
            status["tesseract_available"] = True
        except Exception:
            status["notes"].append(
                "Tesseract binary not found. Install Tesseract OCR and/or set TESSERACT_CMD."
            )
    except Exception:
        status["notes"].append("Install pytesseract via pip.")

    poppler_path = os.getenv("POPPLER_PATH", "").strip()
    status["poppler_path"] = poppler_path
    if not poppler_path:
        status["notes"].append(
            "Set POPPLER_PATH to your Poppler bin folder, or add it to PATH."
        )
    else:
        status["notes"].append(
            "Using POPPLER_PATH from .env for PDF conversion."
        )

    status["ready"] = bool(
        status["pdf2image_installed"]
        and status["pytesseract_installed"]
        and status["tesseract_available"]
    )
    return status


def ocr_pdf_bytes_to_text(pdf_bytes: bytes, *, max_pages: int = 10) -> str:
    """
    Convert up to `max_pages` of a PDF (bytes) into text via OCR.

    Raises ImportError if optional OCR dependencies are missing.
    Raises RuntimeError for conversion/OCR failures.
    """
    try:
        from pdf2image import convert_from_bytes
    except Exception as e:  # pragma: no cover
        raise ImportError("Missing dependency: pdf2image") from e

    try:
        import pytesseract
    except Exception as e:  # pragma: no cover
        raise ImportError("Missing dependency: pytesseract") from e

    # Allow users to point to the Tesseract executable if not on PATH.
    tess_cmd = os.getenv("TESSERACT_CMD", "").strip()
    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd

    try:
        poppler_path = os.getenv("POPPLER_PATH", "").strip() or None
        images = convert_from_bytes(
            pdf_bytes,
            first_page=1,
            last_page=max_pages,
            poppler_path=poppler_path,
        )
    except Exception as e:
        raise RuntimeError(
            "PDF-to-image conversion failed. Set POPPLER_PATH to Poppler bin or add Poppler to PATH."
        ) from e

    parts: list[str] = []
    for img in images:
        try:
            parts.append(pytesseract.image_to_string(img) or "")
        except Exception as e:
            raise RuntimeError("OCR failed while processing a page.") from e

    return "\n".join(p.strip() for p in parts if p and p.strip()).strip()

