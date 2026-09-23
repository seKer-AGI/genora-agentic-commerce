"""Workflow contract shared by all agents."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from genora.core.blocks import Block, ConfirmationBlock
from genora.core.memory import Clarification, PendingAction, SessionState
from genora.core.tools import ToolContext, ToolExecutor, ToolResult
from genora.nlu.intents import IntentResult
from genora.providers.llm import LLMProvider


class WorkflowStatus(enum.StrEnum):
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class WorkflowResult:
    status: WorkflowStatus
    text: str
    blocks: list[Block] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)  # grounded statements an LLM may rephrase
    error_code: str | None = None

    @classmethod
    def ask(cls, state: SessionState, intent: str, slot: str, question: str, options: list[str] | None = None
            ) -> WorkflowResult:
        state.clarification = Clarification(intent=intent, slot=slot, question=question, options=options or [])
        return cls(WorkflowStatus.NEEDS_CLARIFICATION, question, suggestions=options or [])

    @classmethod
    def confirm(cls, state: SessionState, action: PendingAction, text: str, blocks: list[Block] | None = None
                ) -> WorkflowResult:
        state.pending_action = action
        block = ConfirmationBlock(action_id=action.id, summary=action.summary, details=action.details,
                                  expires_at=action.expires_at.isoformat())
        return cls(WorkflowStatus.AWAITING_CONFIRMATION, text, [*(blocks or []), block], ["Yes, confirm", "No, cancel"])

    @classmethod
    def failed(cls, text: str, code: str) -> WorkflowResult:
        return cls(WorkflowStatus.FAILED, text, error_code=code)


class ToolFailed(Exception):
    def __init__(self, result: ToolResult) -> None:
        super().__init__(result.error_message)
        self.result = result


@dataclass
class WorkflowContext:
    text: str
    intent: IntentResult
    state: SessionState
    tool_ctx: ToolContext
    executor: ToolExecutor
    llm: LLMProvider | None = None
    hints: dict[str, Any] = field(default_factory=dict)  # catalog hints: categories, brands
    steps: list[str] = field(default_factory=list)
    status_cb: Callable[[str], None] | None = None

    def status(self, message: str) -> None:
        """Concise, user-facing progress (never internal reasoning)."""
        self.steps.append(message)
        if self.status_cb:
            self.status_cb(message)

    def call(self, tool: str, **args: Any) -> BaseModel:
        result = self.executor.execute(self.tool_ctx, tool, args)
        if not result.ok:
            raise ToolFailed(result)
        assert result.output is not None
        return result.output

    def try_call(self, tool: str, **args: Any) -> ToolResult:
        return self.executor.execute(self.tool_ctx, tool, args)


class Workflow(ABC):
    name: str
    intents: tuple[str, ...]
    description: str = ""

    @abstractmethod
    def run(self, ctx: WorkflowContext) -> WorkflowResult: ...
