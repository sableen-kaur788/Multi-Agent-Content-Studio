"""
Agent 1 — Content Extractor

Pulls raw text from:
- YouTube: official captions via youtube-transcript-api
- Blogs / articles: HTTP fetch + BeautifulSoup main-body heuristics
- PDF: pypdf text extraction from a local file path

Results for a given source string are cached for 1 hour (TTL) to avoid repeat work.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from app.cache import extraction_cache
from app.validators import is_likely_blog_url, is_likely_youtube_url

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_REQUEST_TIMEOUT = 30


def _youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    if "youtu.be" in host:
        vid = (parsed.path or "").strip("/").split("/")[0]
        return vid or None
    if "youtube.com" in host:
        q = parse_qs(parsed.query)
        if "v" in q and q["v"]:
            return q["v"][0]
        m = re.match(r"^/shorts/([^/?#]+)", parsed.path or "")
        if m:
            return m.group(1)
        m = re.match(r"^/embed/([^/?#]+)", parsed.path or "")
        if m:
            return m.group(1)
    return None


def _extract_youtube_sync(url: str) -> str:
    vid = _youtube_video_id(url)
    if not vid:
        raise ValueError("Could not parse YouTube video ID from URL.")
    try:
        # youtube-transcript-api has multiple versions/APIs.
        # We support:
        # - legacy: YouTubeTranscriptApi.get_transcript(video_id, languages=[...])
        # - current: YouTubeTranscriptApi().list(video_id) -> choose transcript -> fetch()
        #
        # Default behavior:
        # - Prefer English ('en') if available
        # - Otherwise fall back to the first available transcript (often auto-generated)
        preferred_langs = ["en"]

        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            try:
                chunks = YouTubeTranscriptApi.get_transcript(  # type: ignore[attr-defined]
                    vid, languages=preferred_langs
                )
            except NoTranscriptFound:
                # Fall back to any available transcript language.
                chunks = YouTubeTranscriptApi.get_transcript(vid)  # type: ignore[attr-defined]
        else:
            api = YouTubeTranscriptApi()
            if not hasattr(api, "list") or not hasattr(api, "fetch"):
                raise RuntimeError(
                    "Unsupported youtube-transcript-api version: missing list/fetch."
                )

            # First try preferred languages (e.g., English), then any available.
            transcript_list = api.list(vid)  # type: ignore[call-arg]
            transcript = None
            for lang in preferred_langs:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    break
                except Exception:
                    transcript = None
            if transcript is None:
                # If English isn't available (e.g., Punjabi videos), pick any transcript.
                try:
                    transcript = transcript_list.find_manually_created_transcript(
                        transcript_list._langs  # type: ignore[attr-defined]
                    )
                except Exception:
                    transcript = None
            if transcript is None:
                # Last resort: pick the first transcript in the list (usually auto-generated).
                transcript = next(iter(transcript_list))

            chunks = transcript.fetch()
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        logger.warning("Transcript unavailable for %s: %s", url, e)
        return _extract_youtube_fallback_sync(url, reason=str(e))
    except Exception as e:
        logger.warning("Transcript extraction failed for %s: %s", url, e)
        return _extract_youtube_fallback_sync(url, reason=str(e))

    # `chunks` can be:
    # - list[dict] (older versions)
    # - FetchedTranscript (iterable of FetchedTranscriptSnippet objects) (newer versions)
    lines: list[str] = []
    for c in chunks:  # type: ignore[assignment]
        if isinstance(c, dict):
            lines.append((c.get("text") or "").strip())
        else:
            # Newer versions return snippet objects with `.text`
            t = getattr(c, "text", None)
            if isinstance(t, str):
                lines.append(t.strip())
            elif c is not None:
                lines.append(str(c).strip())

    text = " ".join([ln for ln in lines if ln]).strip()
    if not text:
        raise RuntimeError(
            "YouTube transcript was empty (captions existed but contained no extractable text)."
        )
    return text


def _extract_youtube_fallback_sync(url: str, *, reason: str) -> str:
    """
    Fallback for cloud IP blocks: fetch watch-page metadata/description.
    This is lower quality than captions but keeps the pipeline usable.
    """
    try:
        r = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(
            "YouTube transcript is unavailable and fallback page fetch also failed. "
            f"Transcript error: {reason}. Fallback error: {e}"
        ) from e

    html = r.text
    title = ""
    description = ""

    m = re.search(r'<meta\s+name="title"\s+content="([^"]*)"', html, flags=re.I)
    if m:
        title = m.group(1).strip()

    # Try ytInitialPlayerResponse JSON for a richer description.
    m = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\});", html, flags=re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            video_details = data.get("videoDetails") or {}
            title = (video_details.get("title") or title or "").strip()
            description = (video_details.get("shortDescription") or "").strip()
        except Exception:
            pass

    if not description:
        m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html, flags=re.I)
        if m:
            description = m.group(1).strip()

    pieces = [
        "[Fallback notice] YouTube captions could not be retrieved from this server IP.",
        f"Reason: {reason}",
    ]
    if title:
        pieces.append(f"Title: {title}")
    if description:
        pieces.append("Description:")
        pieces.append(description)
    text = "\n".join(pieces).strip()
    if len(text) < 80:
        raise RuntimeError(
            "YouTube transcript unavailable and fallback metadata extraction returned very little text. "
            "Try another video, upload a PDF, or use a blog URL."
        )
    return text


def _visible_text_from_soup(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    candidates: list[str] = []
    for sel in ("article", "main", '[role="main"]'):
        el = soup.select_one(sel)
        if el:
            t = el.get_text(separator="\n", strip=True)
            if len(t) > 200:
                candidates.append(t)
    if candidates:
        return max(candidates, key=len)
    body = soup.body
    if body:
        return body.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)


def _extract_blog_sync(url: str) -> str:
    try:
        r = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch blog URL: {e}") from e
    soup = BeautifulSoup(r.content, "html.parser")
    text = _visible_text_from_soup(soup)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 50:
        raise RuntimeError("Extracted very little text from the page; page may be dynamic or blocked.")
    return text


async def extract_content(source: str) -> str:
    """
    Route source to the correct extractor and return raw text.

    - YouTube: transcript lines joined into one string (Agent 1a).
    - Blog URL: fetches HTML and prefers <article>/<main> text (Agent 1b).
    Uses async cache get/set; blocking network and disk work runs in asyncio.to_thread.
    """
    key = source.strip()
    cached = await extraction_cache.get(key)
    if cached is not None:
        return cached

    if is_likely_youtube_url(key):
        text = await asyncio.to_thread(_extract_youtube_sync, key)
    elif is_likely_blog_url(key):
        text = await asyncio.to_thread(_extract_blog_sync, key)
    else:
        raise ValueError("Source is not a supported YouTube URL or blog URL.")

    await extraction_cache.set(key, text)
    return text
