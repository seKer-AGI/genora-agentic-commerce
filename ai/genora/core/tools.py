"""First-class tools: typed contracts, authorization metadata, registry and a guarded executor.

Agents never touch the database. They call tools; the host application implements each tool on top of
its own services. The executor enforces, for every call:

1. the tool exists and is allowed for the calling agent (Nova cannot call Astra tools),
2. the caller holds a required permission (identity comes from the server-side ToolContext only),
3. write/destructive tools only run when explicitly confirmed,
4. inputs validate against the tool's schema (model-generated arguments are untrusted),
5. a per-turn call budget,
and records every call (inputs redacted) for audit/monitoring.
"""

from __future__ import annotations

import enum
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from genora.errors import ToolAuthorizationError, ToolExecutionError, ToolInputError, ToolNotFoundError

logger = logging.getLogger("genora.tools")

I = TypeVar("I", bound=BaseModel)  # noqa: E741
O = TypeVar("O", bound=BaseModel)


class SideEffect(enum.StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


@dataclass
class ToolContext:
    """Server-side identity and request context. Never populated from model/user input."""

    user_id: uuid.UUID
    roles: frozenset[str]
    permissions: frozenset[str]
    agent: str
    seller_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    workflow_id: uuid.UUID | None = None
    attachments: dict[str, tuple[bytes, str]] = field(default_factory=dict)  # id -> (bytes, mime)
    services: Any = None  # host-provided service locator (opaque to GenOra)
    seen_product_ids: set[str] = field(default_factory=set)  # grounding: products returned by tools this turn
    seen_prices: set[str] = field(default_factory=set)  # grounding: prices returned by tools this turn


class Tool(ABC, Generic[I, O]):
    name: ClassVar[str]
    description: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]
    agents: ClassVar[frozenset[str]]
    required_permissions: ClassVar[frozenset[str]] = frozenset()  # ANY of these
    side_effect: ClassVar[SideEffect] = SideEffect.READ
    requires_confirmation: ClassVar[bool] = False

    @abstractmethod
    def run(self, ctx: ToolContext, args: I) -> O: ...

    def summarize(self, output: O) -> dict[str, Any]:
        """Compact, non-sensitive summary of an output for the tool-call log."""
        data = output.model_dump(mode="json")
        return {k: (f"list[{len(v)}]" if isinstance(v, list) else v) for k, v in list(data.items())[:8]
                if not isinstance(v, dict)}

    @classmethod
    def spec(cls) -> dict[str, Any]:
        """OpenAI-compatible function spec (for LLM tool calling)."""
        return {"name": cls.name, "description": cls.description, "parameters": cls.input_model.model_json_schema()}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "name": cls.name,
            "description": cls.description,
            "agents": sorted(cls.agents),
            "required_permissions": sorted(cls.required_permissions),
            "side_effect": cls.side_effect.value,
            "requires_confirmation": cls.requires_confirmation,
            "input_schema": cls.input_model.model_json_schema(),
            "output_schema": cls.output_model.model_json_schema(),
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any, Any]] = {}

    def register(self, tool: Tool[Any, Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name} already registered")
        if tool.side_effect != SideEffect.READ and not tool.requires_confirmation:
            raise ValueError(f"tool {tool.name} has side effects and must require confirmation")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any, Any]:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"unknown tool '{name}'") from exc

    def for_agent(self, agent: str) -> list[Tool[Any, Any]]:
        return [t for t in self._tools.values() if agent in t.agents]

    def names(self) -> list[str]:
        return sorted(self._tools)


@dataclass
class ToolCallRecord:
    tool: str
    status: str  # success | error | denied
    input: dict[str, Any]
    output_summary: dict[str, Any]
    error_code: str | None
    latency_ms: int


class ToolCallRecorder(Protocol):
    def record(self, ctx: ToolContext, record: ToolCallRecord) -> None: ...


class NullRecorder:
    def record(self, ctx: ToolContext, record: ToolCallRecord) -> None:  # noqa: D102
        return None


@dataclass
class ToolResult:
    tool: str
    ok: bool
    output: BaseModel | None = None
    error_code: str | None = None
    error_message: str | None = None
    latency_ms: int = 0


_SENSITIVE = re.compile(r"(pass|secret|token|key|card|cvv|image|bytes)", re.IGNORECASE)


def _redact(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in args.items():
        if _SENSITIVE.search(k):
            out[k] = "<redacted>"
        elif isinstance(v, str) and len(v) > 300:
            out[k] = v[:300] + "…"
        else:
            out[k] = v
    return out


class ConfirmationRequiredError(ToolAuthorizationError):
    code = "CONFIRMATION_REQUIRED"


class ToolBudgetExceededError(ToolExecutionError):
    code = "TOOL_BUDGET_EXCEEDED"


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, recorder: ToolCallRecorder | None = None, max_calls: int = 8,
                 on_status: Callable[[str], None] | None = None) -> None:
        self.registry = registry
        self.recorder = recorder or NullRecorder()
        self.max_calls = max_calls
        self.calls = 0
        self.history: list[ToolCallRecord] = []
        self.on_status = on_status

    def authorize(self, ctx: ToolContext, tool: Tool[Any, Any]) -> None:
        if ctx.agent not in tool.agents:
            raise ToolAuthorizationError(f"tool '{tool.name}' is not available to agent '{ctx.agent}'",
                                         code="TOOL_NOT_ALLOWED_FOR_AGENT")
        if tool.required_permissions and not (tool.required_permissions & ctx.permissions):
            raise ToolAuthorizationError(f"missing permission for tool '{tool.name}'", code="TOOL_NOT_AUTHORIZED")

    def execute(self, ctx: ToolContext, name: str, args: dict[str, Any] | BaseModel, *, confirmed: bool = False
                ) -> ToolResult:
        raw = args.model_dump(mode="json") if isinstance(args, BaseModel) else dict(args)
        started = time.perf_counter()
        try:
            tool = self.registry.get(name)
        except ToolNotFoundError as exc:
            return self._finish(ctx, name, raw, started, "denied", None, exc.code, exc.message)
        try:
            self.authorize(ctx, tool)
            if tool.requires_confirmation and not confirmed:
                raise ConfirmationRequiredError(f"tool '{name}' requires explicit user confirmation")
        except ToolAuthorizationError as exc:
            return self._finish(ctx, name, raw, started, "denied", None, exc.code, exc.message)
        if self.calls >= self.max_calls:
            exc2 = ToolBudgetExceededError("too many tool calls in one turn")
            return self._finish(ctx, name, raw, started, "error", None, exc2.code, exc2.message)
        self.calls += 1
        try:
            parsed = tool.input_model.model_validate(raw)
        except ValidationError as exc:
            msg = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3])
            err = ToolInputError(msg)
            return self._finish(ctx, name, raw, started, "error", None, err.code, err.message)
        try:
            output = tool.run(ctx, parsed)
            if not isinstance(output, tool.output_model):
                output = tool.output_model.model_validate(output)
        except ToolExecutionError as exc:
            return self._finish(ctx, name, raw, started, "error", None, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - never leak internals to the agent/user
            logger.exception("tool_failed", extra={"extra_fields": {"tool": name}})
            return self._finish(ctx, name, raw, started, "error", None, "TOOL_FAILED",
                                f"The {name} tool failed unexpectedly ({type(exc).__name__})")
        return self._finish(ctx, name, raw, started, "success", output, None, None, tool)

    def _finish(self, ctx: ToolContext, name: str, raw: dict[str, Any], started: float, status: str,
                output: BaseModel | None, code: str | None, message: str | None, tool: Tool[Any, Any] | None = None
                ) -> ToolResult:
        latency = int((time.perf_counter() - started) * 1000)
        summary: dict[str, Any] = {}
        if output is not None and tool is not None:
            try:
                summary = tool.summarize(output)
            except Exception:  # noqa: BLE001
                summary = {}
        record = ToolCallRecord(name, status, _redact(raw), summary if status == "success" else {"error": message},
                                code, latency)
        self.history.append(record)
        try:
            self.recorder.record(ctx, record)
        except Exception:  # noqa: BLE001 - recording must never break a workflow
            logger.exception("tool_record_failed")
        return ToolResult(name, status == "success", output, code, message, latency)
