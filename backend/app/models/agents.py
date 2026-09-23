"""GenOra persistence: conversations, messages, sessions, workflows, tool calls."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin, str_enum
from app.models.enums import AgentName, MessageRole, ToolCallStatus, WorkflowStatus


class Conversation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_agent", "user_id", "agent", "updated_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    agent: Mapped[AgentName] = mapped_column(str_enum(AgentName), nullable=False)
    title: Mapped[str | None] = mapped_column(String(160))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", order_by="Message.created_at", cascade="all, delete-orphan"
    )


class Message(UUIDPkMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(str_enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured UI blocks (product cards, comparison tables, …) and metadata.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_workflows.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AgentSession(UUIDPkMixin, TimestampMixin, Base):
    """Short-term working memory for a conversation (slots, referenced products, pending action)."""

    __tablename__ = "agent_sessions"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent: Mapped[AgentName] = mapped_column(str_enum(AgentName), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    pending_action: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentWorkflow(UUIDPkMixin, Base):
    """One execution of an agent workflow (observability + analytics)."""

    __tablename__ = "agent_workflows"
    __table_args__ = (
        Index("ix_agent_workflows_agent_started", "agent", "started_at"),
        Index("ix_agent_workflows_intent", "intent"),
    )

    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_sessions.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    agent: Mapped[AgentName] = mapped_column(str_enum(AgentName), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(str_enum(WorkflowStatus), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    nlu_mode: Mapped[str] = mapped_column(String(16), default="rules", server_default="rules")
    model_name: Mapped[str | None] = mapped_column(String(80))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    steps: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    safety_flags: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    error_code: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tool_calls: Mapped[list[AgentToolCall]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan", order_by="AgentToolCall.created_at"
    )


class AgentToolCall(UUIDPkMixin, Base):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (Index("ix_agent_tool_calls_tool_created", "tool_name", "created_at"),)

    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_workflows.id", ondelete="CASCADE"), index=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ToolCallStatus] = mapped_column(str_enum(ToolCallStatus), nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")  # redacted
    output_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    error_code: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workflow: Mapped[AgentWorkflow] = relationship(back_populates="tool_calls")
