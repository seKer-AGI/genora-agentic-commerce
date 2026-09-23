"""Error types used across the GenOra AI layer."""

from __future__ import annotations

from typing import Any


class GenOraError(Exception):
    code = "GENORA_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.details = details


class ProviderUnavailableError(GenOraError):
    """A configured AI provider (LLM, embeddings, vision, forecasting) cannot be used."""

    code = "PROVIDER_UNAVAILABLE"


class ToolNotFoundError(GenOraError):
    code = "TOOL_NOT_FOUND"


class ToolAuthorizationError(GenOraError):
    code = "TOOL_NOT_AUTHORIZED"


class ToolInputError(GenOraError):
    code = "TOOL_INVALID_INPUT"


class ToolExecutionError(GenOraError):
    """Raised by tool implementations for expected business failures (e.g. product not found)."""

    code = "TOOL_EXECUTION_FAILED"
