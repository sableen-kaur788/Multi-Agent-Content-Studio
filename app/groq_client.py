"""
GroqClient: central wrapper for all Groq chat completions.

Handles model configuration from environment, retries with exponential backoff,
and optional async execution via asyncio.to_thread (Groq SDK is synchronous).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

from groq import Groq
from groq import APIError, APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError

from app.config import get_settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0


class GroqClient:
    """
    Thin wrapper around groq.Groq with retries and shared model config.

    All LLM calls for agents should go through this class for consistent
    behavior and error handling.
    """

    def __init__(self) -> None:
        # Keep initialization cheap; we re-read env on each call so updates are honored
        # after restart and we don't get stuck with a stale/invalid key.
        settings = get_settings()
        self._model = settings["groq_model"]

    @property
    def model(self) -> str:
        return get_settings()["groq_model"]

    def _client(self) -> Groq:
        key = get_settings()["groq_api_key"]
        if not key:
            logger.warning("GROQ_API_KEY is not set; Groq calls will fail.")
        return Groq(api_key=key or "missing")

    def chat_complete_sync(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """
        Synchronous chat completion with exponential backoff (max 3 retries).
        """
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                completion = self._client().chat.completions.create(
                    model=get_settings()["groq_model"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = completion.choices[0].message.content
                if content is None:
                    return ""
                return content.strip()
            except AuthenticationError:
                raise
            except (APIError, APIConnectionError, RateLimitError, APITimeoutError) as e:
                last_error = e
                if attempt == _MAX_RETRIES - 1:
                    break
                delay = _BASE_DELAY * (2**attempt) + random.uniform(0, 0.25)
                logger.warning(
                    "Groq API error (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    e,
                    delay,
                )
                time.sleep(delay)
            except Exception as e:
                last_error = e
                break

        assert last_error is not None
        raise last_error

    async def chat_complete(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Async wrapper: runs blocking Groq SDK in a thread pool."""
        return await asyncio.to_thread(
            self.chat_complete_sync,
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def list_models_sync(self) -> list[dict[str, Any]]:
        """Fetch available models from Groq (OpenAI-compatible models API)."""
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                result = self._client().models.list()
                items: list[dict[str, Any]] = []
                for m in getattr(result, "data", []) or []:
                    mid = getattr(m, "id", None) or (m.get("id") if isinstance(m, dict) else None)
                    if mid:
                        items.append({"id": mid})
                return items
            except AuthenticationError:
                raise
            except (APIError, APIConnectionError, RateLimitError, APITimeoutError) as e:
                last_error = e
                if attempt == _MAX_RETRIES - 1:
                    break
                delay = _BASE_DELAY * (2**attempt) + random.uniform(0, 0.25)
                time.sleep(delay)
            except Exception as e:
                last_error = e
                break
        assert last_error is not None
        raise last_error

    async def list_models(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.list_models_sync)


# Shared instance for the app
groq_client = GroqClient()
