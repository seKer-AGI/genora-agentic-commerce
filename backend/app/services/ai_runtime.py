"""Builds AI providers from configuration (single place that knows about concrete providers)."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from genora.errors import ProviderUnavailableError
from genora.providers.embeddings import (
    EmbeddingProvider,
    FastEmbedProvider,
    HashingEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from genora.providers.llm import LLMProvider, NullLLMProvider, OpenAICompatibleLLMProvider
from genora.providers.vision import LLMVisionProvider, UnavailableVisionProvider, VisionProvider

from app.core.config import get_settings
from app.core.logging import log_event
from app.models.catalog import EMBEDDING_DIM

logger = logging.getLogger("app.ai")


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    s = get_settings()
    if s.embedding_dimensions != EMBEDDING_DIM:
        raise RuntimeError(
            f"EMBEDDING_DIMENSIONS={s.embedding_dimensions} does not match the database column ({EMBEDDING_DIM})"
        )
    if s.embedding_provider == "openai_compatible":
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for EMBEDDING_PROVIDER=openai_compatible")
        return OpenAICompatibleEmbeddingProvider(
            s.openai_api_key.get_secret_value(), s.openai_base_url, s.embedding_model, EMBEDDING_DIM
        )
    if s.embedding_provider == "fastembed":
        try:
            return FastEmbedProvider(dimensions=EMBEDDING_DIM)
        except ProviderUnavailableError as exc:
            log_event(logger, "fastembed_unavailable_falling_back_to_hashing", logging.WARNING, error=exc.message)
    return HashingEmbeddingProvider(EMBEDDING_DIM)


@lru_cache
def get_llm_provider() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "openai_compatible" and s.openai_api_key:
        return OpenAICompatibleLLMProvider(
            s.openai_api_key.get_secret_value(),
            s.openai_base_url,
            s.model_name,
            timeout=s.llm_timeout_seconds,
            temperature=s.llm_temperature,
        )
    return NullLLMProvider()


@lru_cache
def get_vision_provider() -> VisionProvider:
    s = get_settings()
    if s.vision_provider == "openai_compatible" and s.openai_api_key:
        return LLMVisionProvider(
            OpenAICompatibleLLMProvider(
                s.openai_api_key.get_secret_value(), s.openai_base_url, s.vision_model_name,
                timeout=s.llm_timeout_seconds, temperature=0,
            )
        )
    return UnavailableVisionProvider()


def describe_ai_runtime() -> dict[str, Any]:
    """Non-secret description of the active AI configuration (shown in admin UI and /agents/status)."""
    llm = get_llm_provider()
    vision = get_vision_provider()
    emb = get_embedding_provider()
    return {
        "llm": {"provider": llm.name, "model": llm.model, "available": llm.available},
        "nlu_mode": "llm+rules" if llm.available else "rules",
        "embeddings": emb.describe(),
        "vision": {"provider": vision.name, "available": vision.available},
    }
