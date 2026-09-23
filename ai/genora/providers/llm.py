"""Provider-independent LLM interface with an OpenAI-compatible implementation.

The rest of GenOra depends only on :class:`LLMProvider`. Any server exposing the OpenAI
``/chat/completions`` API (OpenAI, Azure OpenAI, vLLM, Ollama, LM Studio, OpenRouter, …) works by
setting ``OPENAI_BASE_URL`` / ``MODEL_NAME``.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from genora.errors import ProviderUnavailableError


@dataclass
class LLMToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0

    def json(self) -> dict[str, Any]:
        """Parse the content as JSON (structured output)."""
        if not self.content:
            raise ValueError("empty LLM response")
        text = self.content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{") :]
        return json.loads(text)


class LLMProvider(ABC):
    name: str
    model: str | None

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int = 800,
    ) -> LLMResponse: ...


class NullLLMProvider(LLMProvider):
    """Used when no model is configured. GenOra then runs in deterministic rule-based mode."""

    name = "none"
    model = None

    @property
    def available(self) -> bool:
        return False

    def complete(self, messages: list[dict[str, Any]], **_: Any) -> LLMResponse:
        raise ProviderUnavailableError("No LLM provider is configured (LLM_PROVIDER=none)")


class OpenAICompatibleLLMProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        timeout: float = 30.0,
        temperature: float = 0.2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    @property
    def available(self) -> bool:
        return True

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int = 800,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": json_schema.get("title", "result"), "schema": json_schema, "strict": False},
            }
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        started = time.perf_counter()
        try:
            resp = self._client.post("/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError(f"LLM request failed: {type(exc).__name__}") from exc
        choice = data["choices"][0]["message"]
        calls = []
        for tc in choice.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(LLMToolCall(id=tc.get("id", ""), name=tc["function"]["name"], arguments=args))
        usage = data.get("usage") or {}
        return LLMResponse(
            content=choice.get("content"),
            tool_calls=calls,
            model=data.get("model", self.model),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
