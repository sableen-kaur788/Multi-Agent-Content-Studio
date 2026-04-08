"""Validate sources for /process (YouTube/blog URLs only)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# YouTube URL patterns (reasonable coverage)
_YT_HOSTS = ("youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com")


def is_valid_http_url(source: str) -> bool:
    parsed = urlparse(source.strip())
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    return True


def is_likely_youtube_url(source: str) -> bool:
    if not is_valid_http_url(source):
        return False
    host = urlparse(source).netloc.lower()
    return any(h in host for h in _YT_HOSTS)


def is_likely_blog_url(source: str) -> bool:
    """Any HTTP(S) URL that is not treated as YouTube is handled as a blog/article URL."""
    return is_valid_http_url(source) and not is_likely_youtube_url(source)


def validate_source(source: str) -> tuple[bool, str]:
    """
    Returns (ok, error_message). Empty error_message when ok is True.
    """
    s = source.strip()
    if not s:
        return False, "Source cannot be empty."

    if is_valid_http_url(s):
        return True, ""

    if re.match(r"^https?://", s, re.I):
        return False, "Invalid URL: missing host or malformed."
    return (
        False,
        "Source must be a valid YouTube/blog http(s) URL. For PDFs, use /process/upload.",
    )
