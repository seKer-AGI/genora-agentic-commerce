"""/api/v1/agents — GenOra Nova / Astra conversations (Apex: planned, returns 501)."""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.runtime import AgentRuntime, Attachment
from app.api.deps import CurrentPrincipal, DbSession
from app.core.config import get_settings
from app.core.errors import AppError, NotImplementedFeature, ValidationFailed
from app.core.rate_limit import rate_limiter
from app.db.session import get_session_factory

router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger("app.agents.api")
AgentPath = Literal["nova", "astra", "apex"]
_IMAGE_MAGIC = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n", "image/webp": b"RIFF"}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    payload: dict[str, Any]
    created_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    agent: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
    memory: dict[str, Any]


class TurnResponse(BaseModel):
    conversation_id: uuid.UUID
    user_message: MessageOut
    message: MessageOut
    workflow: dict[str, Any]
    memory: dict[str, Any]


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class ActionDecision(BaseModel):
    approve: bool


class CreateConversation(BaseModel):
    title: str | None = Field(default=None, max_length=160)


def _msg(m: Any) -> MessageOut:
    return MessageOut(id=m.id, role=m.role.value, content=m.content, payload=m.payload or {}, created_at=m.created_at)


def _turn(out: dict[str, Any]) -> TurnResponse:
    return TurnResponse(conversation_id=out["conversation_id"], user_message=_msg(out["user_message"]),
                        message=_msg(out["message"]), workflow=out["workflow"], memory=out["memory"])


def _limit(principal: Any) -> None:
    rate_limiter.hit(f"agent:{principal.user_id}", 30)


def get_turn_session_factory() -> Callable[[], Session]:
    """Session factory for streamed turns (which outlive the request-scoped session). Overridable in tests."""
    return get_session_factory()


# ------------------------------------------------------------------ status
@router.get("/status")
def agents_status(principal: CurrentPrincipal, db: DbSession) -> dict[str, Any]:
    """Agents, their capabilities/tools, and the active (non-secret) AI runtime configuration."""
    return AgentRuntime(db, principal).status()


@router.get("/apex")
def apex_status() -> dict[str, Any]:
    """GenOra Apex is planned / not implemented. Returns its planned capabilities only."""
    from genora.agents import apex

    return apex.describe()


@router.api_route("/apex/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def apex_not_implemented(path: str) -> Response:
    raise NotImplementedFeature("GenOra Apex is planned and not implemented yet", code="APEX_NOT_IMPLEMENTED")


# ------------------------------------------------------------------ conversations
@router.post("/{agent}/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(agent: AgentPath, principal: CurrentPrincipal, db: DbSession,
                        body: CreateConversation | None = None) -> ConversationOut:
    c = AgentRuntime(db, principal).create_conversation(agent, body.title if body else None)
    return ConversationOut(id=c.id, agent=c.agent.value, title=c.title, created_at=c.created_at, updated_at=c.updated_at)


@router.get("/{agent}/conversations", response_model=list[ConversationOut])
def list_conversations(agent: AgentPath, principal: CurrentPrincipal, db: DbSession) -> list[ConversationOut]:
    rt = AgentRuntime(db, principal)
    rt.authorize(agent)
    return [ConversationOut(id=c.id, agent=c.agent.value, title=c.title, created_at=c.created_at,
                            updated_at=c.updated_at, message_count=n) for c, n in rt.list_conversations(agent)]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> ConversationDetail:
    rt = AgentRuntime(db, principal)
    c = rt.get_conversation(conversation_id)
    msgs = rt.messages(conversation_id)
    return ConversationDetail(id=c.id, agent=c.agent.value, title=c.title, created_at=c.created_at,
                              updated_at=c.updated_at, message_count=len(msgs), messages=[_msg(m) for m in msgs],
                              memory=rt.memory(conversation_id))


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_conversation(conversation_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    AgentRuntime(db, principal).archive(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ turns
@router.post("/conversations/{conversation_id}/messages", response_model=TurnResponse)
def send_message(conversation_id: uuid.UUID, body: SendMessage, principal: CurrentPrincipal, db: DbSession
                 ) -> TurnResponse:
    _limit(principal)
    return _turn(AgentRuntime(db, principal).send(conversation_id, body.content))


@router.post("/conversations/{conversation_id}/messages/image", response_model=TurnResponse)
def send_image(
    conversation_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession,
    file: Annotated[UploadFile, File(description="Product photo (JPEG/PNG/WebP)")],
    content: Annotated[str, Form(max_length=2000)] = "",
) -> TurnResponse:
    _limit(principal)
    mime = (file.content_type or "").lower()
    if mime not in _IMAGE_MAGIC:
        raise ValidationFailed("Only JPEG, PNG or WebP images are supported", code="UNSUPPORTED_MEDIA_TYPE")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit or not data.startswith(_IMAGE_MAGIC[mime]):
        raise ValidationFailed("Invalid or oversized image", code="INVALID_IMAGE")
    att = Attachment(data=data, mime=mime, name=(file.filename or "image")[:100])
    rt = AgentRuntime(db, principal)
    return _turn(rt.send(conversation_id, content or "Find products similar to this image", [att]))


@router.post("/conversations/{conversation_id}/actions/{action_id}", response_model=TurnResponse)
def decide_action(conversation_id: uuid.UUID, action_id: str, body: ActionDecision, principal: CurrentPrincipal,
                  db: DbSession) -> TurnResponse:
    """Explicitly approve or decline a pending agent action (the only way write tools execute besides 'yes')."""
    _limit(principal)
    return _turn(AgentRuntime(db, principal).send(conversation_id, "yes" if body.approve else "no",
                                                  expected_action_id=action_id))


@router.post("/conversations/{conversation_id}/stream")
def stream_message(
    conversation_id: uuid.UUID, body: SendMessage, principal: CurrentPrincipal,
    factory: Annotated[Callable[[], Session], Depends(get_turn_session_factory)],
) -> StreamingResponse:
    """Server-Sent Events: `status` events with concise progress, then one `result` (or `error`) event."""
    _limit(principal)
    events: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

    def worker() -> None:
        db = factory()
        try:
            out = AgentRuntime(db, principal).send(conversation_id, body.content,
                                                   status_cb=lambda m: events.put(("status", {"text": m})))
            events.put(("result", _turn(out).model_dump(mode="json")))
        except AppError as exc:
            events.put(("error", {"code": exc.code, "message": exc.message}))
        except Exception:  # noqa: BLE001
            logger.exception("agent_stream_failed")
            events.put(("error", {"code": "INTERNAL_ERROR", "message": "The assistant failed to respond"}))
        finally:
            db.close()
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen() -> Iterator[str]:
        yield "event: status\ndata: {\"text\": \"Understanding your request…\"}\n\n"
        while True:
            try:
                item = events.get(timeout=120)
            except queue.Empty:
                yield "event: error\ndata: {\"code\": \"TIMEOUT\", \"message\": \"The assistant timed out\"}\n\n"
                return
            if item is None:
                return
            yield f"event: {item[0]}\ndata: {json.dumps(item[1], default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations/{conversation_id}/memory")
def conversation_memory(conversation_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> dict[str, Any]:
    """What the agent currently remembers in this conversation (budget, focus product, pending action…)."""
    return AgentRuntime(db, principal).memory(conversation_id)
